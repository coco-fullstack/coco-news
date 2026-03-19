"""
cloud_news.py - 加密市场智能推送系统 v3
模块：
  daily   - 每日晨报（宏观流动性 + 机构指标 + 衍生品 + 清算数据 + AI摘要 + 决策参考）
  alert   - 即时预警（价格异动 + 极端情绪 + 资金费率异常 + 大额清算）
"""

import json
import os
import re
import smtplib
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote
from html import unescape

# ══════════════════════════════════════════════════════════════════
#  配置
# ══════════════════════════════════════════════════════════════════

CST = timezone(timedelta(hours=8))
COINGECKO = "https://api.coingecko.com/api/v3"

# ── 追踪币种 ──────────────────────────────────────────────────────
TRACKED_COINS = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
    "binancecoin": "BNB", "ripple": "XRP",
    "dogecoin": "DOGE", "cardano": "ADA", "avalanche-2": "AVAX",
    "polkadot": "DOT", "chainlink": "LINK", "sui": "SUI",
    "pepe": "PEPE", "shiba-inu": "SHIB",
    "uniswap": "UNI", "bittensor": "TAO",
}

WATCHLIST_COINS = {
    "uniswap": "UNI",
    "bio-protocol": "BIO",
    "openeden": "EDEN",
    "chainbase": "C",
    "bittensor": "TAO",
    "kiteai": "KITE",
    "pancakeswap-token": "CAKE",
}

STABLECOINS = {"tether": "USDT", "usd-coin": "USDC"}

# ── CoinGecko 兜底源 ID 映射 ─────────────────────────────────────
COINPAPRIKA_IDS = {
    "bitcoin": "btc-bitcoin", "ethereum": "eth-ethereum",
    "solana": "sol-solana", "binancecoin": "bnb-binance-coin",
    "ripple": "xrp-xrp", "dogecoin": "doge-dogecoin",
    "cardano": "ada-cardano", "avalanche-2": "avax-avalanche",
    "polkadot": "dot-polkadot", "chainlink": "link-chainlink",
    "sui": "sui-sui", "pepe": "pepe-pepe", "shiba-inu": "shib-shiba-inu",
    "uniswap": "uni-uniswap", "bittensor": "tao-bittensor",
    "tether": "usdt-tether", "usd-coin": "usdc-usd-coin",
    "pancakeswap-token": "cake-pancakeswap",
}

BINANCE_SYMBOLS = {
    "bitcoin": "BTCUSDT", "ethereum": "ETHUSDT",
    "solana": "SOLUSDT", "binancecoin": "BNBUSDT",
    "ripple": "XRPUSDT", "dogecoin": "DOGEUSDT",
    "cardano": "ADAUSDT", "avalanche-2": "AVAXUSDT",
    "polkadot": "DOTUSDT", "chainlink": "LINKUSDT",
    "sui": "SUIUSDT", "pepe": "PEPEUSDT", "shiba-inu": "SHIBUSDT",
    "uniswap": "UNIUSDT", "bittensor": "TAOUSDT",
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cache")

# ── 阈值 ─────────────────────────────────────────────────────────
PRICE_ALERTS = {
    "BTC": {"above": 120000, "below": 60000},
    "ETH": {"above": 5000, "below": 1500},
    "SOL": {"above": 300, "below": 80},
}
PUMP_THRESHOLD = 10
FUNDING_HOT = 0.03
FUNDING_COLD = 0.0
RSI_OVERBOUGHT = 75
RSI_OVERSOLD = 25
FNG_EXTREME_FEAR = 20

# ── RSS 源 ────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://feeds.feedburner.com/CoinDesk",
    "https://www.theblock.co/rss.xml",
    "https://36kr.com/feed",
]

CRYPTO_KEYWORDS = [
    "BTC", "Bitcoin", "比特币", "ETH", "Ethereum", "以太坊",
    "Solana", "SOL", "XRP", "BNB", "DOGE", "加密货币", "Crypto",
    "cryptocurrency", "币圈", "代币", "token", "交易所", "Binance",
    "Coinbase", "OKX", "稳定币", "stablecoin", "USDT", "USDC",
    "DeFi", "DEX", "NFT", "Web3", "区块链", "blockchain",
    "空投", "airdrop", "质押", "staking", "ETF", "现货ETF",
    "山寨币", "altcoin", "meme币", "CZ", "赵长鹏",
    "Vitalik", "V神", "Michael Saylor", "MicroStrategy",
    "BlackRock", "贝莱德", "Grayscale", "灰度",
    "UNI", "Uniswap", "BIO", "Bio Protocol",
    "EDEN", "OpenEden", "TAO", "Bittensor",
    "CAKE", "PancakeSwap", "KITE", "KiteAI",
    "Chainbase",
]

URGENT_KEYWORDS = [
    "暴跌", "暴涨", "崩盘", "熔断", "跳水", "飙升",
    "历史新高", "历史新低", "all-time high", "ATH",
    "紧急", "突发", "黑天鹅", "重磅", "breaking",
    "crash", "surge", "plunge", "hack", "被盗", "exploit",
]

MAX_NEWS = 8

# ── 清算阈值 ─────────────────────────────────────────────────────
LIQUIDATION_ALERT = 200_000_000  # 24h 清算超 2 亿美金触发预警

# ── 推送配置 ──────────────────────────────────────────────────────
PUSHPLUS_TOKENS = os.environ.get("PUSHPLUS_TOKENS", "").split(",")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# ══════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════

_last_cg_ts = 0  # CoinGecko 全局速率控制

def fetch_json(url: str, timeout: int = 30):
    global _last_cg_ts
    # CoinGecko 免费版限流：自动间隔 2s
    if "coingecko.com" in url:
        import time as _t
        elapsed = _t.time() - _last_cg_ts
        if elapsed < 2:
            _t.sleep(2 - elapsed)
        _last_cg_ts = _t.time()
    req = Request(url, headers={"User-Agent": "MarketBot/2.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[ERROR] {url[:80]}... → {e}")
        return None


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "MarketBot/2.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(text)).strip()


def translate_to_chinese(text: str) -> str:
    if not text or re.search(r'[\u4e00-\u9fff]', text):
        return text
    try:
        encoded = quote(text[:500])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q={encoded}"
        data = fetch_json(url, timeout=10)
        if data:
            return "".join(part[0] for part in data[0] if part[0])
    except Exception:
        pass
    return text


def _safe_fetch(func, default=None):
    """安全调用数据获取函数，出错返回默认值"""
    try:
        return func()
    except Exception as e:
        print(f"[ERROR] {func.__name__} 失败: {e}")
        return default


def _save_cache(filename: str, data):
    """保存数据到本地缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, filename)
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "data": data}
    try:
        with open(cache_path, "w") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] 缓存写入失败 {filename}: {e}")


def _load_cache(filename: str, max_age_hours: int = 24):
    """读取本地缓存，超过 max_age_hours 则返回 None"""
    cache_path = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path) as f:
            payload = json.load(f)
        ts = datetime.fromisoformat(payload["timestamp"])
        if datetime.now(timezone.utc) - ts > timedelta(hours=max_age_hours):
            return None
        return payload["data"]
    except Exception:
        return None


def _fetch_binance_klines(symbol: str, interval: str = "1d", limit: int = 60):
    """从 Binance 获取 K线数据，返回 (closes, volumes) 或 (None, None)"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = fetch_json(url)
    if not data:
        return None, None
    closes = [float(k[4]) for k in data]   # index 4 = close
    volumes = [float(k[5]) for k in data]  # index 5 = volume
    return closes, volumes


# ══════════════════════════════════════════════════════════════════
#  数据获取层
# ══════════════════════════════════════════════════════════════════

def fetch_prices() -> dict:
    all_coins = {**TRACKED_COINS, **WATCHLIST_COINS}
    ids = ",".join(all_coins.keys())
    url = f"{COINGECKO}/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    data = fetch_json(url)
    if data:
        result = {}
        for coin_id, symbol in all_coins.items():
            if coin_id in data:
                result[symbol] = {
                    "price": data[coin_id]["usd"],
                    "change": data[coin_id].get("usd_24h_change", 0) or 0,
                }
        if result:
            return result

    # CoinPaprika 兜底
    print("[WARN] CoinGecko fetch_prices 失败，使用 CoinPaprika 兜底")
    pp_data = fetch_json("https://api.coinpaprika.com/v1/tickers")
    if not pp_data:
        return {}
    pp_by_id = {t["id"]: t for t in pp_data}
    result = {}
    for coin_id, symbol in all_coins.items():
        pp_id = COINPAPRIKA_IDS.get(coin_id)
        if pp_id and pp_id in pp_by_id:
            q = pp_by_id[pp_id].get("quotes", {}).get("USD", {})
            result[symbol] = {
                "price": q.get("price") or 0,
                "change": q.get("percent_change_24h") or 0,
            }
    return result


def fetch_stablecoin_mcap() -> dict:
    ids = ",".join(STABLECOINS.keys())
    url = f"{COINGECKO}/coins/markets?vs_currency=usd&ids={ids}&price_change_percentage=24h"
    data = fetch_json(url)
    if data:
        result = {}
        for coin in data:
            symbol = STABLECOINS.get(coin["id"], coin["symbol"].upper())
            result[symbol] = {
                "mcap": coin.get("market_cap", 0),
                "mcap_change_pct": coin.get("market_cap_change_percentage_24h", 0) or 0,
            }
        if result:
            return result

    # CoinPaprika 兜底
    print("[WARN] CoinGecko fetch_stablecoin_mcap 失败，使用 CoinPaprika 兜底")
    result = {}
    for coin_id, symbol in STABLECOINS.items():
        pp_id = COINPAPRIKA_IDS.get(coin_id)
        if not pp_id:
            continue
        pp = fetch_json(f"https://api.coinpaprika.com/v1/tickers/{pp_id}")
        if pp:
            q = pp.get("quotes", {}).get("USD", {})
            result[symbol] = {
                "mcap": q.get("market_cap") or 0,
                "mcap_change_pct": q.get("market_cap_change_24h") or 0,
            }
    return result


def fetch_fear_greed() -> dict:
    data = fetch_json("https://api.alternative.me/fng/?limit=1")
    if data and "data" in data:
        entry = data["data"][0]
        return {"value": int(entry["value"]), "label": entry["value_classification"]}
    return {}


def fetch_global_data() -> dict:
    data = fetch_json(f"{COINGECKO}/global")
    if data and "data" in data:
        gd = data["data"]
        return {
            "btc_dominance": gd["market_cap_percentage"].get("btc", 0),
            "eth_dominance": gd["market_cap_percentage"].get("eth", 0),
            "total_market_cap": gd["total_market_cap"].get("usd", 0),
            "total_volume": gd["total_volume"].get("usd", 0),
        }

    # CoinPaprika 兜底
    print("[WARN] CoinGecko fetch_global_data 失败，使用 CoinPaprika 兜底")
    pp = fetch_json("https://api.coinpaprika.com/v1/global")
    if not pp:
        return {}
    return {
        "btc_dominance": pp.get("bitcoin_dominance_percentage", 0),
        "eth_dominance": 0,  # CoinPaprika 无 ETH dominance
        "total_market_cap": pp.get("market_cap_usd", 0),
        "total_volume": pp.get("volume_24h_usd", 0),
    }


def fetch_funding_rates() -> dict:
    """Binance 永续合约资金费率"""
    data = fetch_json("https://fapi.binance.com/fapi/v1/premiumIndex")
    if not data:
        return {}
    targets = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    result = {}
    for item in data:
        sym = item.get("symbol", "")
        if sym in targets:
            rate = float(item.get("lastFundingRate", 0)) * 100
            result[sym.replace("USDT", "")] = rate
    return result


# ── 宏观数据 ──────────────────────────────────────────────────────

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

def _fetch_yield_fred(series_id: str, api_key: str) -> dict | None:
    """从 FRED 获取国债收益率"""
    data = fetch_json(
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
        f"&sort_order=desc&limit=2"
    )
    if data and "observations" in data:
        obs = [o for o in data["observations"] if o["value"] != "."]
        if len(obs) >= 2:
            return {"value": float(obs[0]["value"]), "prev": float(obs[1]["value"])}
        elif len(obs) == 1:
            return {"value": float(obs[0]["value"]), "prev": None}
    return None


def _fetch_yield_yahoo(ticker: str) -> dict | None:
    """Yahoo Finance 兜底获取国债收益率"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range=5d&interval=1d"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        valid = [c for c in closes if c is not None]
        if len(valid) >= 2:
            return {"value": valid[-1], "prev": valid[-2]}
        elif valid:
            return {"value": valid[-1], "prev": None}
    except Exception as e:
        print(f"[WARN] Yahoo Finance {ticker} 失败: {e}")
    return None


def fetch_macro_yields() -> dict:
    """获取美国10年期国债 + 日本10年期国债收益率（FRED → Yahoo Finance 兜底）"""
    result = {}
    fred_key = FRED_API_KEY

    # US 10Y
    if fred_key:
        us = _fetch_yield_fred("DGS10", fred_key)
        if us:
            result["US10Y"] = us
    if "US10Y" not in result:
        us = _fetch_yield_yahoo("^TNX")
        if us:
            result["US10Y"] = us

    # JP 10Y
    if fred_key:
        jp = _fetch_yield_fred("IRLTLT01JPM156N", fred_key)
        if jp:
            result["JP10Y"] = jp
    if "JP10Y" not in result:
        jp = _fetch_yield_yahoo("^JGBS")
        if jp:
            result["JP10Y"] = jp

    return result


def fetch_forex() -> dict:
    """获取 USD/JPY, USD/CNY, 100JPY/CNY 汇率"""
    data = fetch_json("https://open.er-api.com/v6/latest/USD")
    if not data or not data.get("rates"):
        return {}
    rates = data["rates"]
    result = {}
    for pair, code in [("USD/JPY", "JPY"), ("USD/CNY", "CNY")]:
        if code in rates:
            result[pair] = rates[code]
    # 100日元兑人民币 — 用 JPY 基准直接获取
    jpy_data = fetch_json("https://open.er-api.com/v6/latest/JPY")
    if jpy_data and jpy_data.get("rates", {}).get("CNY"):
        result["100JPY/CNY"] = jpy_data["rates"]["CNY"] * 100
    return result


# ── RSI 计算 ─────────────────────────────────────────────────────

def calculate_rsi(prices_list: list[float], period: int = 14) -> float | None:
    if len(prices_list) < period + 1:
        return None
    deltas = [prices_list[i] - prices_list[i - 1] for i in range(1, len(prices_list))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def fetch_rsi(coin_id: str = "bitcoin", days: int = 30) -> float | None:
    url = f"{COINGECKO}/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    data = fetch_json(url)
    if data and "prices" in data:
        return calculate_rsi([p[1] for p in data["prices"]])

    # Binance Klines 兜底
    binance_sym = BINANCE_SYMBOLS.get(coin_id)
    if not binance_sym:
        return None
    print(f"[WARN] CoinGecko fetch_rsi({coin_id}) 失败，使用 Binance 兜底")
    closes, _ = _fetch_binance_klines(binance_sym, "1d", max(days, 30))
    if closes:
        return calculate_rsi(closes)
    return None


# ── 多空持仓比 (Binance) ─────────────────────────────────────────

def fetch_long_short_ratio() -> dict:
    """Binance 全网多空持仓人数比"""
    result = {}
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=1"
        data = fetch_json(url)
        if data and len(data) > 0:
            name = symbol.replace("USDT", "")
            ratio = float(data[0].get("longShortRatio", 1))
            long_pct = float(data[0].get("longAccount", 0.5)) * 100
            result[name] = {"ratio": ratio, "long_pct": long_pct}
    return result


# ── Gas Fee (ETH) ────────────────────────────────────────────────

def fetch_gas_fee() -> dict:
    """获取 ETH Gas 费（通过公开 API）"""
    # 方案1: Etherscan 免费端点（不需要 key 的 gas tracker）
    data = fetch_json("https://api.etherscan.io/api?module=gastracker&action=gasoracle")
    if data and data.get("status") == "1":
        result = data.get("result", {})
        return {
            "low": int(result.get("SafeGasPrice", 0)),
            "standard": int(result.get("ProposeGasPrice", 0)),
            "fast": int(result.get("FastGasPrice", 0)),
        }

    # 方案2: 备用 - 通过 ETH RPC 粗略估算
    rpc_data = fetch_json(
        "https://ethereum-rpc.publicnode.com",
    )
    # 如果上面也失败，返回空
    return {}


# ── DeFi TVL (DeFiLlama) ────────────────────────────────────────

def fetch_defi_tvl() -> dict:
    """获取 DeFi 总 TVL 及主要协议"""
    # 总 TVL
    data = fetch_json("https://api.llama.fi/v2/historicalChainTvl")
    if not data or len(data) < 2:
        return {}
    latest = data[-1]
    prev = data[-2]
    total_tvl = latest.get("tvl", 0)
    prev_tvl = prev.get("tvl", 0)
    change_pct = ((total_tvl - prev_tvl) / prev_tvl * 100) if prev_tvl > 0 else 0

    result = {
        "total_tvl": total_tvl,
        "change_pct": change_pct,
        "protocols": [],
    }

    # Top 协议 TVL
    protocols = fetch_json("https://api.llama.fi/protocols")
    if protocols:
        top = sorted(protocols, key=lambda x: x.get("tvl") or 0, reverse=True)[:5]
        for p in top:
            tvl = p.get("tvl", 0)
            change_1d = p.get("change_1d", 0) or 0
            result["protocols"].append({
                "name": p.get("name", ""),
                "tvl": tvl,
                "change_1d": change_1d,
            })

    return result


# ── 期权交割日 (Deribit) ──────────────────────────────────────────

def _calc_max_pain(strikes_data: dict) -> float | None:
    """计算 Max Pain（最大痛点价格）
    strikes_data: {strike: {"call_oi": float, "put_oi": float}}
    """
    if not strikes_data:
        return None
    all_strikes = sorted(strikes_data.keys())
    if len(all_strikes) < 2:
        return None

    min_pain = float("inf")
    max_pain_strike = None
    for settle in all_strikes:
        total = 0.0
        for strike, ois in strikes_data.items():
            # Call holders lose when settle > strike
            total += max(0, settle - strike) * ois.get("call_oi", 0)
            # Put holders lose when settle < strike
            total += max(0, strike - settle) * ois.get("put_oi", 0)
        if total < min_pain:
            min_pain = total
            max_pain_strike = settle
    return max_pain_strike


def fetch_options_expiry() -> dict:
    """获取 BTC/ETH 期权到期日及未平仓量 + Max Pain (Deribit 公开 API)"""
    result = {}
    for currency in ["BTC", "ETH"]:
        url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
        data = fetch_json(url)
        if not data or "result" not in data:
            continue

        # 按到期日汇总未平仓量 + 按行权价记录 call/put OI
        expiry_oi = {}
        expiry_strikes = {}  # {expiry_str: {strike: {"call_oi": x, "put_oi": y}}}
        for item in data["result"]:
            name = item.get("instrument_name", "")
            oi = float(item.get("open_interest", 0))
            underlying = float(item.get("underlying_price", 0))
            if oi <= 0:
                continue
            parts = name.split("-")
            if len(parts) >= 4:
                expiry_str = parts[1]
                try:
                    strike = float(parts[2])
                except ValueError:
                    continue
                opt_type = parts[3]  # "C" or "P"

                if expiry_str not in expiry_oi:
                    expiry_oi[expiry_str] = {"oi_coins": 0, "underlying": underlying}
                expiry_oi[expiry_str]["oi_coins"] += oi

                if expiry_str not in expiry_strikes:
                    expiry_strikes[expiry_str] = {}
                if strike not in expiry_strikes[expiry_str]:
                    expiry_strikes[expiry_str][strike] = {"call_oi": 0, "put_oi": 0}
                if opt_type == "C":
                    expiry_strikes[expiry_str][strike]["call_oi"] += oi
                else:
                    expiry_strikes[expiry_str][strike]["put_oi"] += oi

        expiries = []
        for exp_str, info in expiry_oi.items():
            notional = info["oi_coins"] * info["underlying"]
            try:
                exp_date = datetime.strptime(exp_str, "%d%b%y")
            except ValueError:
                continue
            days_left = (exp_date - datetime.now()).days
            if days_left < 0:
                continue
            max_pain = _calc_max_pain(expiry_strikes.get(exp_str, {}))
            expiries.append({
                "date": exp_str,
                "date_fmt": exp_date.strftime("%Y-%m-%d"),
                "days_left": days_left,
                "oi_coins": info["oi_coins"],
                "notional_usd": notional,
                "is_major": notional >= 1_000_000_000,
                "max_pain": max_pain,
            })

        expiries.sort(key=lambda x: x["days_left"])
        result[currency] = expiries[:5]

    return result


# ── 逐币爆仓/持仓数据 (Binance) ──────────────────────────────────

def fetch_coin_liquidations() -> dict:
    """获取 BTC/ETH 独立的未平仓量、买卖比、多空比"""
    import time as _time
    result = {}
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        coin = symbol.replace("USDT", "")
        info = {}

        # 当前未平仓量
        oi_data = fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}")
        if oi_data:
            info["open_interest"] = float(oi_data.get("openInterest", 0))

        # 未平仓量历史 (计算变动)
        oi_hist = fetch_json(
            f"https://fapi.binance.com/futures/data/openInterestHist"
            f"?symbol={symbol}&period=1d&limit=2"
        )
        if oi_hist and len(oi_hist) >= 2:
            curr_oi = float(oi_hist[-1].get("sumOpenInterestValue", 0))
            prev_oi = float(oi_hist[-2].get("sumOpenInterestValue", 0))
            info["oi_value_usd"] = curr_oi
            info["oi_change_pct"] = ((curr_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0

        # 主动买卖比 (清算方向代理)
        taker = fetch_json(
            f"https://fapi.binance.com/futures/data/takerlongshortRatio"
            f"?symbol={symbol}&period=1d&limit=1"
        )
        if taker and len(taker) > 0:
            info["buy_vol"] = float(taker[0].get("buyVol", 0))
            info["sell_vol"] = float(taker[0].get("sellVol", 0))
            info["buy_sell_ratio"] = float(taker[0].get("buySellRatio", 1))

        # 多空持仓人数比
        ls = fetch_json(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            f"?symbol={symbol}&period=1d&limit=1"
        )
        if ls and len(ls) > 0:
            info["long_ratio"] = float(ls[0].get("longAccount", 0.5)) * 100

        if info:
            result[coin] = info
        _time.sleep(0.3)

    return result


# ── 机构持仓 + 大额动向 (CoinGecko Public Treasury) ──────────────

def fetch_institutional_holdings() -> dict:
    """获取 BTC/ETH 机构持仓数据（公开上市公司）"""
    import time as _time
    result = {}
    for coin in ["bitcoin", "ethereum"]:
        url = f"{COINGECKO}/companies/public_treasury/{coin}"
        data = fetch_json(url)
        if not data or "companies" not in data:
            continue
        sym = "BTC" if coin == "bitcoin" else "ETH"
        companies = []
        for c in data["companies"][:10]:
            companies.append({
                "name": c.get("name", ""),
                "symbol": c.get("symbol", ""),
                "holdings": c.get("total_holdings", 0),
                "value_usd": c.get("total_current_value_usd", 0),
                "pct_supply": c.get("percentage_of_total_supply", 0),
            })
        result[sym] = {
            "total_holdings": data.get("total_holdings", 0),
            "total_value_usd": data.get("total_value_usd", 0),
            "top_companies": companies,
        }
        _time.sleep(1)

    if result:
        _save_cache("institutional.json", result)
        return result

    # 本地缓存兜底（无免费替代 API）
    print("[WARN] CoinGecko fetch_institutional_holdings 失败，使用本地缓存兜底")
    cached = _load_cache("institutional.json", max_age_hours=24)
    return cached if cached else {}


# ── Top 200 涨幅筛选 vs BTC (CoinGecko) ─────────────────────────

def _fetch_binance_symbols() -> set:
    """获取 Binance 现货上市的所有币种符号"""
    data = fetch_json("https://api.binance.com/api/v3/exchangeInfo")
    if not data or "symbols" not in data:
        return set()
    symbols = set()
    for s in data["symbols"]:
        if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
            symbols.add(s["baseAsset"].upper())
    print(f"[INFO] Binance 上市币种: {len(symbols)}")
    return symbols


def fetch_top200_vs_btc() -> dict:
    """市值前300币种，筛选 Binance 上市 + 各时间维度跑赢BTC
    分为前200和200名后，维度：周(7d)、月(30d)、年(1y)
    """
    import time as _time

    # 获取 Binance 上市列表
    binance_coins = _fetch_binance_symbols()

    all_coins = []
    for page in [1, 2, 3]:
        url = (
            f"{COINGECKO}/coins/markets?vs_currency=usd"
            f"&order=market_cap_desc&per_page=100&page={page}"
            f"&price_change_percentage=7d,30d,1y&sparkline=false"
        )
        data = fetch_json(url)
        if data:
            all_coins.extend(data)
        _time.sleep(2)

    if not all_coins:
        # CoinPaprika 兜底
        print("[WARN] CoinGecko fetch_top200_vs_btc 失败，使用 CoinPaprika 兜底")
        pp_data = fetch_json("https://api.coinpaprika.com/v1/tickers?quotes=USD")
        if not pp_data:
            return {}
        pp_coins = sorted(pp_data, key=lambda x: x.get("rank", 9999))[:300]
        btc_pp = next((c for c in pp_coins if c.get("id") == "btc-bitcoin"), None)
        if not btc_pp:
            return {}
        btc_q = btc_pp.get("quotes", {}).get("USD", {})
        btc_7d = btc_q.get("percent_change_7d") or 0
        btc_30d = btc_q.get("percent_change_30d") or 0
        btc_1y = btc_q.get("percent_change_1y") or 0

        stable_syms = {"USDT", "USDC", "DAI", "FDUSD", "USDE", "USDS", "TUSD", "USDP", "FRAX", "USDD", "BUSD", "PYUSD"}
        result = {
            "btc_benchmark": {"7d": btc_7d, "30d": btc_30d, "1y": btc_1y},
            "outperformers": {"7d": [], "30d": [], "1y": []},
            "total_coins": 0,
            "binance_count": len(binance_coins),
        }
        filtered = [c for c in pp_coins if c.get("symbol", "") not in stable_syms][:300]
        result["total_coins"] = len(filtered)

        for coin in filtered:
            if coin.get("id") == "btc-bitcoin":
                continue
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            rank = coin.get("rank", 0)
            on_binance = sym in binance_coins if binance_coins else True
            q = coin.get("quotes", {}).get("USD", {})
            c7d = q.get("percent_change_7d") or 0
            c30d = q.get("percent_change_30d") or 0
            c1y = q.get("percent_change_1y") or 0
            entry = {
                "symbol": sym, "name": name, "rank": rank,
                "price": q.get("price", 0),
                "mcap": q.get("market_cap", 0),
                "binance": on_binance,
            }
            if c7d > btc_7d:
                result["outperformers"]["7d"].append({**entry, "change": c7d, "vs_btc": c7d - btc_7d})
            if c30d > btc_30d:
                result["outperformers"]["30d"].append({**entry, "change": c30d, "vs_btc": c30d - btc_30d})
            if c1y > btc_1y:
                result["outperformers"]["1y"].append({**entry, "change": c1y, "vs_btc": c1y - btc_1y})

        for period in ["7d", "30d", "1y"]:
            result["outperformers"][period].sort(key=lambda x: x["vs_btc"], reverse=True)
        return result

    btc_data = next((c for c in all_coins if c["id"] == "bitcoin"), None)
    if not btc_data:
        return {}

    btc_7d = btc_data.get("price_change_percentage_7d_in_currency") or 0
    btc_30d = btc_data.get("price_change_percentage_30d_in_currency") or 0
    btc_1y = btc_data.get("price_change_percentage_1y_in_currency") or 0

    stable_ids = {"tether", "usd-coin", "dai", "first-digital-usd", "ethena-usde",
                  "usds", "true-usd", "paxos-standard", "frax", "usdd",
                  "binance-peg-busd", "paypal-usd"}

    result = {
        "btc_benchmark": {"7d": btc_7d, "30d": btc_30d, "1y": btc_1y},
        "outperformers": {"7d": [], "30d": [], "1y": []},
        "total_coins": 0,
        "binance_count": len(binance_coins),
    }

    coins = [c for c in all_coins if c.get("id") not in stable_ids][:300]
    result["total_coins"] = len(coins)

    for coin in coins:
        if coin["id"] == "bitcoin":
            continue
        sym = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        rank = coin.get("market_cap_rank", 0)

        # 标记是否 Binance 上市
        on_binance = sym in binance_coins if binance_coins else True

        c7d = coin.get("price_change_percentage_7d_in_currency") or 0
        c30d = coin.get("price_change_percentage_30d_in_currency") or 0
        c1y = coin.get("price_change_percentage_1y_in_currency") or 0

        entry = {
            "symbol": sym, "name": name, "rank": rank,
            "price": coin.get("current_price", 0),
            "mcap": coin.get("market_cap", 0),
            "binance": on_binance,
        }

        if c7d > btc_7d:
            result["outperformers"]["7d"].append({**entry, "change": c7d, "vs_btc": c7d - btc_7d})
        if c30d > btc_30d:
            result["outperformers"]["30d"].append({**entry, "change": c30d, "vs_btc": c30d - btc_30d})
        if c1y > btc_1y:
            result["outperformers"]["1y"].append({**entry, "change": c1y, "vs_btc": c1y - btc_1y})

    for period in ["7d", "30d", "1y"]:
        result["outperformers"][period].sort(key=lambda x: x["vs_btc"], reverse=True)

    return result


# ── 趋势评分系统 ─────────────────────────────────────────────────

def calculate_trend_score(data: dict) -> int:
    """综合所有指标计算 0-100 的市场趋势评分
    50=中性, >70=偏多, <30=偏空
    """
    score = 50  # 基准分

    # 恐贪指数 (权重大)
    fng = data.get("fng", {}).get("value", 50)
    if fng >= 70:
        score += 10
    elif fng >= 55:
        score += 5
    elif fng <= 25:
        score -= 12
    elif fng <= 40:
        score -= 6

    # BTC RSI
    btc_rsi = data.get("btc_rsi")
    if btc_rsi is not None:
        if btc_rsi >= 70:
            score += 8
        elif btc_rsi >= 55:
            score += 3
        elif btc_rsi <= 30:
            score -= 10
        elif btc_rsi <= 40:
            score -= 5

    # BTC 24h 涨跌
    btc = data.get("prices", {}).get("BTC", {})
    btc_change = btc.get("change", 0)
    if btc_change > 5:
        score += 8
    elif btc_change > 2:
        score += 4
    elif btc_change < -5:
        score -= 8
    elif btc_change < -2:
        score -= 4

    # 资金费率
    funding = data.get("funding", {})
    if funding:
        avg_rate = sum(funding.values()) / len(funding)
        if avg_rate > 0.05:
            score -= 5  # 过热反而扣分
        elif avg_rate > 0.01:
            score += 3
        elif avg_rate < -0.01:
            score -= 5

    # 稳定币流入
    usdt = data.get("stablecoins", {}).get("USDT", {})
    mcap_change = usdt.get("mcap_change_pct", 0)
    if mcap_change > 0.5:
        score += 5
    elif mcap_change < -0.3:
        score -= 5

    # DeFi TVL
    defi = data.get("defi_tvl", {})
    tvl_change = defi.get("change_pct", 0)
    if tvl_change > 2:
        score += 4
    elif tvl_change < -2:
        score -= 4

    # 多空比
    ls = data.get("long_short", {}).get("BTC", {})
    if ls:
        if ls.get("long_pct", 50) > 65:
            score -= 3  # 散户过度做多=反指标
        elif ls.get("long_pct", 50) < 35:
            score += 3  # 散户过度做空=反指标

    # 清算
    liq = data.get("liquidations", {})
    if liq.get("total_24h", 0) >= LIQUIDATION_ALERT:
        long_ratio = liq.get("long_ratio", 50)
        if long_ratio > 60:
            score -= 6  # 多头大清算=偏空
        else:
            score += 4  # 空头被清=偏多

    return max(0, min(100, score))


def trend_label(score: int) -> tuple[str, str]:
    """返回趋势标签和 CSS class"""
    if score >= 75:
        return "强势看多", "g"
    elif score >= 60:
        return "偏多", "g"
    elif score >= 45:
        return "中性", "b"
    elif score >= 30:
        return "偏空", "y"
    else:
        return "强势看空", "r"


# ── 历史数据归档 ─────────────────────────────────────────────────

def archive_snapshot(data: dict):
    """保存当日数据快照为 JSON"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    archive_dir = "data/snapshots"
    os.makedirs(archive_dir, exist_ok=True)

    snapshot = {
        "date": today,
        "timestamp": datetime.now(CST).isoformat(),
        "btc_price": data.get("prices", {}).get("BTC", {}).get("price"),
        "eth_price": data.get("prices", {}).get("ETH", {}).get("price"),
        "fng": data.get("fng", {}).get("value"),
        "btc_rsi": data.get("btc_rsi"),
        "total_market_cap": data.get("global", {}).get("total_market_cap"),
        "btc_dominance": data.get("global", {}).get("btc_dominance"),
        "defi_tvl": data.get("defi_tvl", {}).get("total_tvl"),
        "funding_btc": data.get("funding", {}).get("BTC"),
        "liquidation_24h": data.get("liquidations", {}).get("total_24h"),
        "trend_score": data.get("trend_score"),
    }

    filepath = os.path.join(archive_dir, f"{today}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"[OK] 快照已保存: {filepath}")


# ── 清算数据 (Coinglass) ──────────────────────────────────────────

def fetch_liquidations() -> dict:
    """获取全网清算数据（Coinglass 公开端点）"""
    # Coinglass 公开 API: 24h 清算汇总
    url = "https://open-api.coinglass.com/public/v2/liquidation/info?time_type=1"
    data = fetch_json(url)
    if not data or data.get("code") != "0":
        # 备用：尝试 Coinglass v3 公开端点
        url2 = "https://open-api-v3.coinglass.com/api/futures/liquidation/info?time_type=1"
        data = fetch_json(url2)
        if not data or data.get("code") != "0":
            print("[WARN] 清算数据获取失败，使用 Binance 备用")
            return _fetch_liquidations_binance()

    info = data.get("data", {})
    return {
        "total_24h": info.get("totalVolUsd", 0),
        "long_24h": info.get("longVolUsd", 0),
        "short_24h": info.get("shortVolUsd", 0),
        "long_ratio": info.get("longRate", 0),
    }


def _fetch_liquidations_binance() -> dict:
    """备用：从 Binance 获取近期大额清算订单估算"""
    # Binance 没有直接的清算汇总 API，用强平订单流估算
    url = "https://fapi.binance.com/fapi/v1/allForceOrders?limit=100"
    data = fetch_json(url)
    if not data:
        return {}
    total = sum(float(o.get("origQty", 0)) * float(o.get("price", 0)) for o in data)
    longs = sum(float(o.get("origQty", 0)) * float(o.get("price", 0))
                for o in data if o.get("side") == "SELL")  # 多头被清算=卖出
    shorts = total - longs
    return {
        "total_24h": total,
        "long_24h": longs,
        "short_24h": shorts,
        "long_ratio": (longs / total * 100) if total > 0 else 50,
        "source": "binance_sample",
    }


# ── AI 新闻摘要 (Claude API) ────────────────────────────────────

def _ai_call(prompt: str, max_tokens: int = 300, temperature: float = 0.3) -> str:
    """统一 AI 调用：Gemini 优先 → Groq 兜底"""
    # ── Gemini ──
    if GEMINI_API_KEY:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                print(f"[OK] Gemini 响应 ({len(text)} 字)")
                return text
        except Exception as e:
            print(f"[WARN] Gemini 调用失败: {e}，尝试 Groq 兜底")

    # ── Groq 兜底 ──
    if GROQ_API_KEY:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {GROQ_API_KEY}",
                     "User-Agent": "Mozilla/5.0"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                text = result["choices"][0]["message"]["content"]
                print(f"[OK] Groq 响应 ({len(text)} 字)")
                return text
        except Exception as e:
            body = ""
            if hasattr(e, "read"):
                try:
                    body = e.read().decode()
                except Exception:
                    pass
            print(f"[ERROR] Groq 调用失败: {e} {body}")

    print("[SKIP] AI 未配置 (需要 GEMINI_API_KEY 或 GROQ_API_KEY)")
    return ""


def generate_ai_summary(news: list[dict], prices: dict, fng: dict) -> str:
    """AI 生成 3 句话的今日要点"""
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        print("[SKIP] AI 未配置，跳过摘要")
        return ""

    titles = [item.get("title_cn", item["title"]) for item in news[:15]]
    titles_text = "\n".join(f"- {t}" for t in titles)
    btc = prices.get("BTC", {})
    eth = prices.get("ETH", {})
    fng_val = fng.get("value", "N/A")

    prompt = f"""你是一位加密市场分析师。根据以下今日新闻标题和市场数据，用中文写出3句话的「今日要点」摘要。

要求：
- 只写3句话，每句话聚焦一个核心主题
- 语言简洁专业，像彭博终端的快讯风格
- 如果新闻有明显利好/利空倾向，直接点明
- 不要废话和套话

市场数据：
BTC: {_p(btc.get('price', 0))} ({'+' if btc.get('change', 0) >= 0 else ''}{btc.get('change', 0):.1f}%)
ETH: {_p(eth.get('price', 0))} ({'+' if eth.get('change', 0) >= 0 else ''}{eth.get('change', 0):.1f}%)
恐贪指数: {fng_val}

今日新闻：
{titles_text}"""

    return _ai_call(prompt, max_tokens=300, temperature=0.3)


def _ai_filter_urgent_news(news_items: list[dict]) -> list[dict]:
    """用 AI 判断紧急新闻是否值得推送"""
    if (not GEMINI_API_KEY and not GROQ_API_KEY) or not news_items:
        return news_items

    titles = "\n".join(
        f"{i+1}. {n.get('title_cn', n['title'])}" for i, n in enumerate(news_items[:10])
    )
    prompt = f"""你是加密市场新闻编辑。以下是今日标记为"紧急"的新闻标题，请判断哪些是真正重大事件值得立即推送。

判断标准：
- 重大价格异动（暴涨暴跌>5%）、交易所被黑、监管重大政策、ETF批准/拒绝、项目重大事故
- 日常波动、普通融资、常规升级、营销活动 → 不推送
- 标题党、重复信息 → 不推送

新闻列表：
{titles}

请只返回值得推送的新闻序号（从1开始），用逗号分隔。如果都不值得推送，返回"无"。"""

    text = _ai_call(prompt, max_tokens=100, temperature=0.1)
    if not text:
        return news_items

    print(f"[AI] 紧急新闻过滤结果: {text}")
    if "无" in text or text == "0":
        return []

    indices = []
    for part in re.findall(r"\d+", text):
        idx = int(part) - 1
        if 0 <= idx < len(news_items):
            indices.append(idx)

    filtered = [news_items[i] for i in indices]
    print(f"[AI] 保留 {len(filtered)}/{len(news_items)} 条紧急新闻")
    return filtered


# ── RSS 新闻 ─────────────────────────────────────────────────────

def parse_feed(xml_text: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        if title:
            items.append({"title": title, "link": link, "description": desc})
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", "", ns) or "").strip()
            if title:
                items.append({"title": title, "link": link, "description": desc})
    return items


def fetch_news() -> list[dict]:
    """抓取 RSS 新闻，过滤币圈相关，翻译标题，标记来源"""
    source_map = {
        "cointelegraph": "CoinTelegraph",
        "coindesk": "CoinDesk",
        "theblock": "The Block",
        "36kr": "36Kr",
    }
    all_items = []
    for feed_url in RSS_FEEDS:
        print(f"[INFO] 抓取: {feed_url}")
        try:
            xml_text = fetch_text(feed_url)
        except (URLError, OSError) as e:
            print(f"[ERROR] 失败: {e}")
            continue
        items = parse_feed(xml_text)
        source = next((v for k, v in source_map.items() if k in feed_url.lower()), feed_url.split("/")[2])
        for item in items:
            item["source"] = source
        print(f"[INFO] {len(items)} 条")
        all_items.extend(items)

    # 去重 + 过滤币圈/金融相关
    seen = set()
    filtered = []
    for item in all_items:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        combined = f"{item['title']} {item['description']}".lower()
        if any(kw.lower() in combined for kw in CRYPTO_KEYWORDS):
            item["title_cn"] = translate_to_chinese(item["title"])
            desc = strip_html(item["description"]).replace("\n", " ")
            if len(desc) > 80:
                desc = desc[:80] + "..."
            item["summary_cn"] = translate_to_chinese(desc) if desc else ""
            item["urgent"] = any(kw.lower() in combined for kw in URGENT_KEYWORDS)
            filtered.append(item)
    return filtered


def fetch_watchlist_news() -> dict:
    """从 RSS 抓取关注币种相关新闻"""
    all_news = fetch_news()
    result = {}
    for cg_id, symbol in WATCHLIST_COINS.items():
        keywords = [symbol.lower(), cg_id.replace("-", " ")]
        matched = []
        for n in all_news:
            text = f"{n['title']} {n.get('description', '')}".lower()
            if any(kw in text for kw in keywords):
                matched.append(n)
        if matched:
            result[symbol] = matched
    return result


# ══════════════════════════════════════════════════════════════════
#  Apple 风格极简 HTML 模板
# ══════════════════════════════════════════════════════════════════

STYLE = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:-apple-system,'SF Pro Display','Helvetica Neue','PingFang SC',sans-serif;
  background:#f5f5f7;
  color:#1d1d1f;padding:24px 16px;
  -webkit-font-smoothing:antialiased
}
.c{
  max-width:560px;margin:0 auto;
  background:#ffffff;
  border-radius:24px;overflow:hidden;
  border:1px solid #e5e5ea;
  box-shadow:0 12px 48px rgba(0,0,0,0.08),0 2px 6px rgba(0,0,0,0.04)
}
.hd{
  padding:36px 32px 20px;
  background:#ffffff;
  border-bottom:1px solid #e5e5ea;
  color:#1d1d1f
}
.hd h1{font-size:22px;font-weight:700;letter-spacing:-.5px;margin-bottom:4px;color:#1a1a1a}
.hd .sub{font-size:11px;color:#86868b;font-weight:400;letter-spacing:1.5px;text-transform:uppercase}
.hd .t{font-size:12px;color:#86868b;margin-top:8px;font-variant-numeric:tabular-nums}
.s{padding:24px 32px;border-top:1px solid #f0f0f0}
.st{
  font-size:10px;font-weight:600;color:#86868b;
  text-transform:uppercase;letter-spacing:1.5px;
  margin-bottom:14px;
  padding-left:10px;
  border-left:3px solid #86868b
}
.r{
  padding:8px 0;font-size:13px;line-height:1.4;overflow:hidden
}
.r .l{color:#6e6e73;font-weight:400;float:left}
.r .v{font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.2px;color:#1d1d1f;float:right;text-align:right}
.up{color:#34c759;font-weight:700}.dn{color:#ff3b30;font-weight:700}.nt{color:#b0b0b0}
.tg{
  display:inline-block;font-size:9px;font-weight:600;
  padding:3px 8px;border-radius:6px;margin-left:6px;
  letter-spacing:.3px;text-transform:uppercase
}
.tg-r{background:#fff2f1;color:#ff3b30}
.tg-b{background:#eef3fe;color:#007aff}
.tg-g{background:#eef8f0;color:#34c759}
.tg-y{background:#fff8ec;color:#ff9500}
.dv{height:1px;background:#f0f0f0;margin:6px 0}
.ab{
  margin:8px 0;padding:14px 16px;border-radius:14px;
  font-size:12px;line-height:1.6
}
.ab-d{background:#fff2f1;border:1px solid #fcd9d6}
.ab-i{background:#f5f5f7;border:1px solid #e5e5ea}
.sb{
  background:#f5f5f7;
  border:1px solid #e5e5ea;
  border-radius:14px;padding:16px 18px;margin-top:10px;
  font-size:12px;line-height:1.8;color:#48484a
}
.ni{
  padding:12px 16px;margin:8px 0;font-size:12px;line-height:1.6;
  background:#f5f5f7;border-radius:12px;
  border-left:3px solid #d1d1d6
}
.ni a{color:#1d1d1f;text-decoration:none;font-weight:500}
.ni a:hover{text-decoration:underline}
.ni .sm{color:#86868b;font-size:11px;margin-top:2px}
.ft{
  padding:20px 32px;text-align:center;
  font-size:10px;color:#aeaeb2;letter-spacing:.3px;
  border-top:1px solid #f0f0f0
}
.ft span{color:#86868b;font-weight:600}
</style>"""


def _p(price: float) -> str:
    """格式化价格"""
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:.2f}"
    elif price >= 0.001:
        return f"${price:.4f}"
    return f"${price:.8f}"


def _c(change: float) -> str:
    """格式化涨跌幅"""
    if change >= 0:
        return f'<span class="up">▲ +{change:.1f}%</span>'
    else:
        return f'<span class="dn">▼ {change:.1f}%</span>'


def _mc(value: float) -> str:
    """格式化市值"""
    if value >= 1e12:
        return f"${value/1e12:.2f}T"
    if value >= 1e9:
        return f"${value/1e9:.1f}B"
    if value >= 1e6:
        return f"${value/1e6:.0f}M"
    return f"${value:,.0f}"


def _arrow(curr, prev) -> str:
    """变动箭头"""
    if prev is None:
        return ""
    diff = curr - prev
    if abs(diff) < 0.001:
        return '<span class="nt">—</span>'
    cls = "up" if diff > 0 else "dn"
    sign = "+" if diff > 0 else ""
    return f'<span class="{cls}">{sign}{diff:.2f}</span>'


def _ftag(text: str, cls: str) -> str:
    return f'<span class="tg tg-{cls}">{text}</span>'


# ══════════════════════════════════════════════════════════════════
#  可视化组件 (纯 HTML/CSS，邮件兼容)
# ══════════════════════════════════════════════════════════════════

def _vis_gauge(value: int, label: str, max_val: int = 100) -> str:
    """横条仪表盘（恐贪指数等 0-100 值）— 邮件兼容 table 布局"""
    pct = max(0, min(100, value / max_val * 100))
    remain = 100 - pct
    # 颜色：Apple 系统色 — 红(极度恐惧) → 橙(恐惧) → 灰(中性) → 蓝(贪婪) → 靛蓝(极度贪婪)
    if pct <= 25:
        color = "#ff3b30"
    elif pct <= 45:
        color = "#ff9500"
    elif pct <= 55:
        color = "#86868b"
    elif pct <= 75:
        color = "#007aff"
    else:
        color = "#5856d6"

    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:12px 0 8px">
<tr>
<td style="padding:0">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td style="width:{pct:.0f}%;height:10px;border-radius:5px 0 0 5px" bgcolor="{color}"></td>
    <td style="width:{remain:.0f}%;height:10px;border-radius:0 5px 5px 0" bgcolor="#e5e5ea"></td>
    <td style="width:90px;padding-left:10px;font-size:18px;font-weight:700;color:#1d1d1f;white-space:nowrap;vertical-align:middle" rowspan="1">{value} · <span style="font-size:11px;font-weight:600;color:{color}">{label}</span></td>
  </tr>
  </table>
</td>
</tr>
<tr>
<td style="padding:0">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:2px">
  <tr>
    <td style="font-size:9px;color:#bbb;text-align:left;width:33%">←极度恐惧</td>
    <td style="font-size:9px;color:#bbb;text-align:center;width:34%">中性</td>
    <td style="font-size:9px;color:#bbb;text-align:right;width:33%">极度贪婪→</td>
  </tr>
  </table>
</td>
</tr>
</table>'''


def _vis_progress_bar(long_pct: float, symbol: str) -> str:
    """多空比彩色进度条 — 邮件兼容 table 布局"""
    short_pct = 100 - long_pct
    long_w = max(5, long_pct)
    short_w = max(5, short_pct)
    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 10px">
<tr>
<td style="font-size:10px;color:#999;padding-bottom:3px">{symbol} 多 {long_pct:.1f}%</td>
<td style="font-size:10px;color:#999;padding-bottom:3px;text-align:right">空 {short_pct:.1f}%</td>
</tr>
<tr><td colspan="2" style="padding:0">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="width:{long_w:.1f}%;height:8px;border-radius:4px 0 0 4px" bgcolor="#34a853"></td>
    <td style="width:{short_w:.1f}%;height:8px;border-radius:0 4px 4px 0" bgcolor="#ea4335"></td>
  </tr></table>
</td></tr>
</table>'''


def _vis_bar_chart(items: list[dict], value_key: str = "vs_btc",
                   label_key: str = "symbol", max_items: int = 5) -> str:
    """水平条形图（涨幅筛选、机构持仓等）"""
    if not items:
        return ""
    display = items[:max_items]
    max_val = max(abs(item[value_key]) for item in display) if display else 1
    if max_val == 0:
        max_val = 1

    rows = ""
    for item in display:
        val = item[value_key]
        w = abs(val) / max_val * 100
        w = max(8, min(95, w))
        remain_w = 100 - w
        color = "#34a853" if val >= 0 else "#ea4335"
        label = item[label_key]
        rows += f'''<tr>
<td style="width:50px;color:#6e6e73;font-size:11px;padding:3px 0;white-space:nowrap">{label}</td>
<td style="padding:3px 8px">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="width:{w:.0f}%;height:16px;border-radius:3px" bgcolor="{color}"></td>
    <td style="width:{remain_w:.0f}%;height:16px" bgcolor="#f5f5f5"></td>
  </tr></table>
</td>
<td style="width:55px;text-align:right;font-weight:600;color:{color};font-size:11px;font-variant-numeric:tabular-nums;padding:3px 0;white-space:nowrap">{val:+.1f}%</td>
</tr>'''

    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0">{rows}</table>'


def _vis_timeline(expiries: list[dict], currency: str) -> str:
    """期权到期时间轴 — 表格横条图（邮件兼容 table 布局）"""
    if not expiries:
        return ""
    max_notional = max(e["notional_usd"] for e in expiries) if expiries else 1
    if max_notional == 0:
        max_notional = 1

    rows = ""
    for exp in expiries[:6]:
        days = exp["days_left"]
        notional = exp["notional_usd"]
        bar_pct = max(8, int(notional / max_notional * 100))
        remain_pct = 100 - bar_pct
        # 颜色编码：<=3天红、<=7天橙、>7天金
        if days <= 3:
            color = "#ea4335"
        elif days <= 7:
            color = "#f4a261"
        else:
            color = "#86868b"
        star = " ★" if exp["is_major"] else ""
        nv = _mc(notional)
        mp = exp.get("max_pain")
        mp_html = f'<span style="color:#ff9500;font-size:9px"> MP{_p(mp)}</span>' if mp else ""
        rows += f'''<tr>
<td style="font-size:11px;color:#6e6e73;padding:3px 0;white-space:nowrap;width:50px">{exp["date_fmt"]}</td>
<td style="font-size:10px;color:#999;padding:3px 6px;white-space:nowrap;width:40px;text-align:right">{days}天</td>
<td style="padding:3px 0">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="width:{bar_pct}%;height:8px;border-radius:4px 0 0 4px" bgcolor="{color}"></td>
    <td style="width:{remain_pct}%;height:8px" bgcolor="#f5f5f5"></td>
  </tr></table>
</td>
<td style="font-size:11px;font-weight:600;color:#1d1d1f;padding:3px 0 3px 8px;white-space:nowrap;width:80px;text-align:right">{nv}{star}{mp_html}</td>
</tr>'''

    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 12px">
<tr><td colspan="4" style="font-size:10px;color:#86868b;padding-bottom:6px;font-weight:600">{currency} 到期时间轴</td></tr>
{rows}
</table>'''


def _vis_holdings_bars(companies: list[dict], max_items: int = 5) -> str:
    """机构持仓比例条（类 treemap 横条）— 邮件兼容 table 布局"""
    if not companies:
        return ""
    total = sum(c["value_usd"] for c in companies[:max_items])
    if total == 0:
        return ""

    colors = ["#007aff", "#5856d6", "#34c759", "#ff9500", "#af52de"]
    cells = ""
    for i, comp in enumerate(companies[:max_items]):
        pct = comp["value_usd"] / total * 100
        if pct < 2:
            continue
        color = colors[i % len(colors)]
        name = comp["name"][:12]
        cells += f'<td style="width:{pct:.1f}%;height:24px;text-align:center;font-size:8px;color:#fff;font-weight:600;white-space:nowrap;overflow:hidden" bgcolor="{color}">{name}</td>'

    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0;border-radius:6px;overflow:hidden"><tr>{cells}</tr></table>'''


def _vis_rsi_bar(rsi_value: float, symbol: str) -> str:
    """RSI 进度条 — 邮件兼容 table 布局"""
    if rsi_value is None:
        return ""
    rsi = max(0, min(100, rsi_value))
    remain = 100 - rsi
    # 颜色：<=30 蓝色(超卖) / 30-70 金色(中性) / >=70 红色(超买)
    if rsi <= 30:
        color = "#4285f4"
        tag = "超卖"
    elif rsi >= 70:
        color = "#ea4335"
        tag = "超买"
    else:
        color = "#86868b"
        tag = ""
    tag_html = f' <span style="font-size:9px;font-weight:600;color:{color}">{tag}</span>' if tag else ""
    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 8px">
<tr>
<td style="font-size:11px;color:#6e6e73;padding-bottom:3px;width:60px">{symbol} RSI</td>
<td style="padding-bottom:3px">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="width:{rsi:.0f}%;height:7px;border-radius:4px 0 0 4px" bgcolor="{color}"></td>
    <td style="width:{remain:.0f}%;height:7px;border-radius:0 4px 4px 0" bgcolor="#e5e5ea"></td>
  </tr></table>
</td>
<td style="font-size:12px;font-weight:600;color:#1d1d1f;padding-bottom:3px;padding-left:8px;width:60px;text-align:right;white-space:nowrap">{rsi:.0f}{tag_html}</td>
</tr>
<tr><td></td>
<td style="padding:0">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="font-size:8px;color:#ccc;text-align:left;width:33%">30</td>
    <td style="font-size:8px;color:#ccc;text-align:center;width:34%">50</td>
    <td style="font-size:8px;color:#ccc;text-align:right;width:33%">70</td>
  </tr></table>
</td>
<td></td></tr>
</table>'''


def _vis_funding_heatmap(funding: dict) -> str:
    """资金费率热力图 — 邮件兼容 table 布局"""
    if not funding:
        return ""
    cells_top = ""
    cells_bottom = ""
    for sym in ["BTC", "ETH", "SOL"]:
        if sym not in funding:
            continue
        rate = funding[sym]
        # 颜色映射：过热红 / 过冷蓝 / 中性绿
        if rate > FUNDING_HOT:
            color = "#ea4335"
            tag = "过热"
        elif rate < FUNDING_COLD:
            color = "#4285f4"
            tag = "过冷"
        else:
            color = "#34a853"
            tag = "中性"
        cells_top += f'''<td style="padding:6px;text-align:center;width:33%">
<span style="font-size:12px;font-weight:700;color:#1d1d1f">{sym}</span> <span style="color:{color};font-size:14px">&#9632;</span>
<br><span style="font-size:11px;font-weight:600;color:{color}">{rate:.4f}%</span>
</td>'''
        cells_bottom += f'<td style="font-size:9px;color:#999;text-align:center;padding:0 6px">({tag})</td>'

    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 10px;background:#f5f5f7;border:1px solid #e5e5ea;border-radius:8px">
<tr><td colspan="3" style="font-size:10px;color:#86868b;padding:8px 10px 4px;font-weight:600">费率热力图</td></tr>
<tr>{cells_top}</tr>
<tr>{cells_bottom}</tr>
<tr><td colspan="3" style="height:6px"></td></tr>
</table>'''


def _vis_mini_sparkline(rates: list, trend_label: str, trend_cls: str = "b") -> str:
    """费率趋势迷你柱状图 — 邮件兼容 table 布局"""
    if not rates or len(rates) < 2:
        return ""
    # 归一化到 2-16px 高度
    min_r = min(rates)
    max_r = max(rates)
    rng = max_r - min_r if max_r != min_r else 1
    cells = ""
    for r in rates:
        h = 2 + int((r - min_r) / rng * 14)
        # 颜色：正值金色，负值蓝色
        color = "#007aff" if r >= 0 else "#5856d6"
        cells += f'<td style="vertical-align:bottom;padding:0 1px"><div style="width:6px;height:{h}px;border-radius:1px;background:{color}"></div></td>'

    tag = _ftag(trend_label, trend_cls)
    return f'''<table cellpadding="0" cellspacing="0" border="0" style="margin:2px 0">
<tr>
<td style="font-size:11px;color:#6e6e73;padding-right:8px;vertical-align:middle">费率趋势</td>
<td style="vertical-align:middle">
  <table cellpadding="0" cellspacing="0" border="0"><tr>{cells}</tr></table>
</td>
<td style="padding-left:8px;vertical-align:middle">{tag}</td>
</tr></table>'''


# ══════════════════════════════════════════════════════════════════
#  交易策略指标
# ══════════════════════════════════════════════════════════════════

def fetch_strategy_indicators() -> dict:
    """获取 BTC/ETH 关键交易策略指标：MA 位置、MACD 方向、成交量趋势、资金费率趋势"""
    import time as _time
    result = {}

    for coin_id, symbol in [("bitcoin", "BTC"), ("ethereum", "ETH")]:
        info = {}

        # 获取 60天价格数据，计算 MA、MACD、成交量趋势
        url = f"{COINGECKO}/coins/{coin_id}/market_chart?vs_currency=usd&days=60&interval=daily"
        data = fetch_json(url)
        closes = None
        volumes = None
        if data and "prices" in data:
            closes = [p[1] for p in data["prices"]]
            volumes = [v[1] for v in data.get("total_volumes", [])]
        else:
            binance_sym = BINANCE_SYMBOLS.get(coin_id)
            if binance_sym:
                print(f"[WARN] CoinGecko fetch_strategy_indicators({coin_id}) 失败，使用 Binance 兜底")
                closes, volumes = _fetch_binance_klines(binance_sym, "1d", 60)

        if not closes or len(closes) < 30:
            continue

        current_price = closes[-1]

        # MA7 / MA25 / MA50
        ma7 = sum(closes[-7:]) / 7
        ma25 = sum(closes[-25:]) / 25
        ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None

        info["price"] = current_price
        info["ma7"] = ma7
        info["ma25"] = ma25
        info["ma50"] = ma50

        # MA 信号：价格 vs MA 位置
        if current_price > ma7 > ma25:
            info["ma_signal"] = "多头排列"
            info["ma_class"] = "g"
        elif current_price < ma7 < ma25:
            info["ma_signal"] = "空头排列"
            info["ma_class"] = "r"
        elif current_price > ma25:
            info["ma_signal"] = "偏多"
            info["ma_class"] = "g"
        else:
            info["ma_signal"] = "偏空"
            info["ma_class"] = "r"

        # MACD (12,26,9) 简化版
        if len(closes) >= 26:
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            dif = ema12 - ema26
            # 信号线：DIF 的 9日 EMA（近似用 SMA）
            if len(closes) >= 35:
                dif_series = []
                for i in range(9):
                    idx = len(closes) - 9 + i
                    e12 = _ema(closes[:idx+1], 12)
                    e26 = _ema(closes[:idx+1], 26)
                    dif_series.append(e12 - e26)
                dea = sum(dif_series) / len(dif_series)
                macd_hist = (dif - dea) * 2
                info["macd_dif"] = dif
                info["macd_dea"] = dea
                info["macd_hist"] = macd_hist
                if dif > dea and macd_hist > 0:
                    info["macd_signal"] = "金叉+红柱"
                    info["macd_class"] = "g"
                elif dif > dea:
                    info["macd_signal"] = "金叉"
                    info["macd_class"] = "g"
                elif dif < dea and macd_hist < 0:
                    info["macd_signal"] = "死叉+绿柱"
                    info["macd_class"] = "r"
                else:
                    info["macd_signal"] = "死叉"
                    info["macd_class"] = "r"

        # 成交量分析：近7天 vs 前7天
        if len(volumes) >= 14:
            recent_vol = sum(volumes[-7:]) / 7
            prev_vol = sum(volumes[-14:-7]) / 7
            if prev_vol > 0:
                vol_change = (recent_vol - prev_vol) / prev_vol * 100
                info["vol_change"] = vol_change
                info["vol_7d_avg"] = recent_vol
                if vol_change > 30:
                    info["vol_signal"] = "放量"
                    info["vol_class"] = "r"
                elif vol_change > 10:
                    info["vol_signal"] = "温和放量"
                    info["vol_class"] = "y"
                elif vol_change < -30:
                    info["vol_signal"] = "缩量"
                    info["vol_class"] = "b"
                else:
                    info["vol_signal"] = "正常"
                    info["vol_class"] = "g"

        # 支撑/阻力位（近30天最高/最低 + 关键均线）
        high_30d = max(closes[-30:])
        low_30d = min(closes[-30:])
        info["resistance"] = high_30d
        info["support"] = low_30d
        info["price_vs_range"] = (current_price - low_30d) / (high_30d - low_30d) * 100 if high_30d != low_30d else 50

        result[symbol] = info
        _time.sleep(1)

    # 获取资金费率历史趋势（Binance 近3次费率）
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        coin = symbol.replace("USDT", "")
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=3"
        fr_data = fetch_json(url)
        if fr_data and len(fr_data) >= 2 and coin in result:
            rates = [float(r.get("fundingRate", 0)) * 100 for r in fr_data]
            result[coin]["funding_rates"] = rates
            trend = rates[-1] - rates[0]
            if trend > 0.005:
                result[coin]["funding_trend"] = "上升"
                result[coin]["funding_trend_class"] = "r"
            elif trend < -0.005:
                result[coin]["funding_trend"] = "下降"
                result[coin]["funding_trend_class"] = "g"
            else:
                result[coin]["funding_trend"] = "平稳"
                result[coin]["funding_trend_class"] = "b"

    return result


def _ema(data: list[float], period: int) -> float:
    """计算 EMA"""
    if len(data) < period:
        return data[-1] if data else 0
    multiplier = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def generate_ai_strategy(indicators: dict, fng: dict, funding: dict) -> str:
    """AI 分析策略指标，输出交易研判"""
    if (not GEMINI_API_KEY and not GROQ_API_KEY) or not indicators:
        return ""

    lines = []
    for sym in ["BTC", "ETH"]:
        if sym not in indicators:
            continue
        ind = indicators[sym]
        lines.append(f"\n{sym}:")
        lines.append(f"  价格: {_p(ind.get('price', 0))}")
        lines.append(f"  均线: MA7={_p(ind.get('ma7',0))} MA25={_p(ind.get('ma25',0))} MA50={_p(ind.get('ma50',0) or 0)} → {ind.get('ma_signal','')}")
        if "macd_signal" in ind:
            lines.append(f"  MACD: {ind['macd_signal']} (DIF={ind.get('macd_dif',0):.2f} DEA={ind.get('macd_dea',0):.2f})")
        lines.append(f"  30天区间: 支撑{_p(ind.get('support',0))} 阻力{_p(ind.get('resistance',0))} 位置{ind.get('price_vs_range',50):.0f}%")
        if "vol_signal" in ind:
            lines.append(f"  成交量: {ind['vol_signal']} ({ind.get('vol_change',0):+.0f}%)")
        if "funding_trend" in ind:
            lines.append(f"  费率趋势: {ind['funding_trend']}")

    fng_val = fng.get("value", "N/A")
    fund_str = ", ".join(f"{k}={v:.4f}%" for k, v in funding.items()) if funding else "无"
    context = "\n".join(lines)

    prompt = f"""你是一位专业加密货币交易策略分析师。根据以下BTC和ETH的技术指标数据，给出简洁的交易策略建议。

数据：
恐贪指数: {fng_val}
资金费率: {fund_str}
{context}

要求：
- 分别给BTC和ETH各2-3句话的策略分析
- 包含：当前趋势判断、关键支撑阻力位、操作建议（做多/做空/观望/减仓）
- 如果指标出现背离或矛盾信号，明确指出
- 风格：专业简洁，像交易员的盘前笔记
- 用中文回答"""

    return _ai_call(prompt, max_tokens=400, temperature=0.3)


def _build_strategy_html(indicators: dict, ai_analysis: str = "") -> str:
    """构建交易策略指标 HTML 区块"""
    if not indicators:
        return ""

    h = '<div class="s"><p class="st" style="border-left-color:#007aff">交易策略指标</p>'

    # AI 策略研判（放在最前面）
    if ai_analysis:
        h += f'<div class="sb">{ai_analysis.replace(chr(10), "<br>")}</div>'

    for sym in ["BTC", "ETH"]:
        if sym not in indicators:
            continue
        ind = indicators[sym]
        price = ind.get("price", 0)
        ma_sig = ind.get("ma_signal", "—")
        ma_cls = ind.get("ma_class", "b")

        # ── 币种卡片 ──
        h += f'''<div style="background:#f5f5f7;border:1px solid #e5e5ea;border-radius:14px;padding:16px 18px;margin-top:12px">'''

        # 卡片标题行：币种 + 当前价格 + 均线信号标签
        h += f'''<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="font-size:15px;font-weight:700;color:#1d1d1f">{sym} <span style="font-weight:400;color:#86868b;font-size:12px">{_p(price)}</span></td>
<td style="text-align:right">{_ftag(ma_sig, ma_cls)}</td>
</tr></table>'''

        # ── 均线矩阵 ──
        ma7 = ind.get("ma7", 0)
        ma25 = ind.get("ma25", 0)
        ma50 = ind.get("ma50")

        # 判断价格与各 MA 的关系
        def _ma_rel(p, ma):
            if ma == 0:
                return "#86868b"
            return "#34c759" if p >= ma else "#ff3b30"

        ma7_color = _ma_rel(price, ma7)
        ma25_color = _ma_rel(price, ma25)

        ma_cols = f'''<td style="width:33%;text-align:center;padding:8px 4px">
<div style="font-size:9px;color:#86868b;text-transform:uppercase;letter-spacing:1px">MA7</div>
<div style="font-size:13px;font-weight:700;color:#1d1d1f;margin-top:2px">{_p(ma7)}</div>
<div style="font-size:9px;font-weight:600;color:{ma7_color};margin-top:1px">{'▲ 上方' if price >= ma7 else '▼ 下方'}</div>
</td>
<td style="width:33%;text-align:center;padding:8px 4px;border-left:1px solid #e5e5ea;border-right:1px solid #e5e5ea">
<div style="font-size:9px;color:#86868b;text-transform:uppercase;letter-spacing:1px">MA25</div>
<div style="font-size:13px;font-weight:700;color:#1d1d1f;margin-top:2px">{_p(ma25)}</div>
<div style="font-size:9px;font-weight:600;color:{ma25_color};margin-top:1px">{'▲ 上方' if price >= ma25 else '▼ 下方'}</div>
</td>'''

        if ma50:
            ma50_color = _ma_rel(price, ma50)
            ma_cols += f'''<td style="width:34%;text-align:center;padding:8px 4px">
<div style="font-size:9px;color:#86868b;text-transform:uppercase;letter-spacing:1px">MA50</div>
<div style="font-size:13px;font-weight:700;color:#1d1d1f;margin-top:2px">{_p(ma50)}</div>
<div style="font-size:9px;font-weight:600;color:{ma50_color};margin-top:1px">{'▲ 上方' if price >= ma50 else '▼ 下方'}</div>
</td>'''
        else:
            ma_cols += '<td style="width:34%"></td>'

        h += f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:10px;background:#ffffff;border-radius:10px;border:1px solid #e5e5ea">
<tr>{ma_cols}</tr></table>'''

        # ── 30天价格区间进度条 ──
        support = ind.get("support", 0)
        resist = ind.get("resistance", 0)
        price_pos = ind.get("price_vs_range", 50)
        remain_pos = 100 - price_pos
        # 价格位置颜色：靠近支撑红、靠近阻力绿、中间蓝
        if price_pos <= 30:
            pos_color = "#ff3b30"
        elif price_pos >= 70:
            pos_color = "#34c759"
        else:
            pos_color = "#007aff"

        h += f'''<div style="margin-top:12px">
<div style="font-size:10px;color:#86868b;margin-bottom:4px;font-weight:600">30天价格区间 · 当前位置 <span style="color:{pos_color};font-weight:700">{price_pos:.0f}%</span></div>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td colspan="2" style="padding:0">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="width:{price_pos:.0f}%;height:8px;border-radius:4px 0 0 4px" bgcolor="{pos_color}"></td>
    <td style="width:{remain_pos:.0f}%;height:8px;border-radius:0 4px 4px 0" bgcolor="#e5e5ea"></td>
  </tr></table>
</td></tr>
<tr>
<td style="font-size:9px;color:#aeaeb2;padding-top:3px">支撑 {_p(support)}</td>
<td style="font-size:9px;color:#aeaeb2;padding-top:3px;text-align:right">阻力 {_p(resist)}</td>
</tr></table>
</div>'''

        # ── MACD + 成交量 并排指标行 ──
        macd_html = ""
        vol_html = ""

        if "macd_signal" in ind:
            macd_cls = ind.get("macd_class", "b")
            macd_sig = ind["macd_signal"]
            dif = ind.get("macd_dif", 0)
            dea = ind.get("macd_dea", 0)
            hist = ind.get("macd_hist", 0)
            hist_color = "#34c759" if hist >= 0 else "#ff3b30"
            macd_html = f'''<td style="width:50%;padding:10px 12px;vertical-align:top">
<div style="font-size:9px;color:#86868b;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">MACD</div>
<div style="margin-bottom:4px">{_ftag(macd_sig, macd_cls)}</div>
<div style="font-size:10px;color:#636366;line-height:1.6">DIF <span style="font-weight:600">{dif:.2f}</span></div>
<div style="font-size:10px;color:#636366;line-height:1.6">DEA <span style="font-weight:600">{dea:.2f}</span></div>
<div style="font-size:10px;color:{hist_color};font-weight:600;line-height:1.6">柱 {hist:+.2f}</div>
</td>'''

        if "vol_signal" in ind:
            vol_cls = ind.get("vol_class", "b")
            vol_chg = ind.get("vol_change", 0)
            vol_avg = ind.get("vol_7d_avg", 0)
            vol_arrow = "▲" if vol_chg >= 0 else "▼"
            vol_color = "#34c759" if vol_chg >= 0 else "#ff3b30"
            vol_avg_str = _mc(vol_avg) if vol_avg else "—"
            vol_html = f'''<td style="width:50%;padding:10px 12px;vertical-align:top;border-left:1px solid #e5e5ea">
<div style="font-size:9px;color:#86868b;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">成交量 7D</div>
<div style="margin-bottom:4px">{_ftag(ind["vol_signal"], vol_cls)}</div>
<div style="font-size:10px;color:#636366;line-height:1.6">均量 <span style="font-weight:600">{vol_avg_str}</span></div>
<div style="font-size:10px;color:{vol_color};font-weight:600;line-height:1.6">{vol_arrow} {vol_chg:+.0f}% vs 前周</div>
</td>'''

        if macd_html or vol_html:
            if not macd_html:
                macd_html = '<td style="width:50%"></td>'
            if not vol_html:
                vol_html = '<td style="width:50%"></td>'
            h += f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:10px;background:#ffffff;border-radius:10px;border:1px solid #e5e5ea">
<tr>{macd_html}{vol_html}</tr></table>'''

        # ── 资金费率趋势 ──
        if "funding_trend" in ind:
            ft_cls = ind.get("funding_trend_class", "b")
            rates = ind.get("funding_rates", [])
            h += '<div style="margin-top:10px">'
            if rates:
                h += _vis_mini_sparkline(rates, ind["funding_trend"], ft_cls)
            else:
                h += f'<div class="r"><span class="l">费率趋势</span><span class="v">{_ftag(ind["funding_trend"], ft_cls)}</span></div>'
            h += '</div>'

        h += '</div>'  # 关闭卡片

    h += '</div>'
    return h


# ══════════════════════════════════════════════════════════════════
#  每日晨报 (Daily Digest)
# ══════════════════════════════════════════════════════════════════

def build_daily_html(data: dict) -> str:
    now = datetime.now(CST)
    d, t = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")

    prices = data.get("prices", {})
    stables = data.get("stablecoins", {})
    forex = data.get("forex", {})
    fng = data.get("fng", {})
    gd = data.get("global", {})
    funding = data.get("funding", {})
    yields = data.get("yields", {})
    btc_rsi = data.get("btc_rsi")
    eth_rsi = data.get("eth_rsi")
    news = data["news"]
    ls = data.get("long_short", {})
    gas = data.get("gas_fee", {})
    defi = data.get("defi_tvl", {})
    liq = data.get("liquidations", {})

    h = f'<!DOCTYPE html><html><head><meta charset="utf-8">{STYLE}</head><body><div class="c">'

    # ═══ Header: BTC/ETH 核心指标 + 趋势评分 ═══
    score = data.get("trend_score", 50)
    slabel, _ = trend_label(score)
    btc = prices.get("BTC", {})
    eth = prices.get("ETH", {})
    fng_val = fng.get("value", 0)
    # 恐贪标签
    if fng_val <= 25:
        fng_tag = "极度恐惧"
    elif fng_val <= 45:
        fng_tag = "恐惧"
    elif fng_val <= 55:
        fng_tag = "中性"
    elif fng_val <= 75:
        fng_tag = "贪婪"
    else:
        fng_tag = "极度贪婪"

    # ETH/BTC 汇率
    btc_price = btc.get('price', 0)
    eth_price = eth.get('price', 0)
    eth_btc = eth_price / btc_price if btc_price > 0 else 0

    # 生成 BTC/ETH 卡片颜色
    btc_chg = btc.get('change', 0)
    eth_chg = eth.get('change', 0)
    btc_bg = '#f0faf2' if btc_chg >= 0 else '#fef2f1'
    btc_border = '#34c759' if btc_chg >= 0 else '#ff3b30'
    btc_arrow = '▲' if btc_chg >= 0 else '▼'
    btc_sign = '+' if btc_chg >= 0 else ''
    eth_bg = '#f0faf2' if eth_chg >= 0 else '#fef2f1'
    eth_border = '#34c759' if eth_chg >= 0 else '#ff3b30'
    eth_arrow = '▲' if eth_chg >= 0 else '▼'
    eth_sign = '+' if eth_chg >= 0 else ''

    h += f"""<div class="hd">
      <p class="sub">DAILY BRIEFING</p>
      <h1>Market Digest</h1>
      <p class="t">{d} · {t} CST</p>
      <table style="width:100%;margin-top:16px;border-collapse:separate;border-spacing:8px 0">
        <tr>
          <td style="width:50%;padding:14px 16px;border-radius:12px;background:{btc_bg};border:1px solid {btc_border}20">
            <div style="font-size:11px;font-weight:600;color:#86868b;margin-bottom:4px">BTC</div>
            <div style="font-size:18px;font-weight:700;color:#1d1d1f">{_p(btc.get('price', 0))}</div>
            <div style="font-size:13px;font-weight:700;color:{btc_border};margin-top:2px">{btc_arrow} {btc_sign}{btc_chg:.1f}%</div>
          </td>
          <td style="width:50%;padding:14px 16px;border-radius:12px;background:{eth_bg};border:1px solid {eth_border}20">
            <div style="font-size:11px;font-weight:600;color:#86868b;margin-bottom:4px">ETH</div>
            <div style="font-size:18px;font-weight:700;color:#1d1d1f">{_p(eth.get('price', 0))}</div>
            <div style="font-size:13px;font-weight:700;color:{eth_border};margin-top:2px">{eth_arrow} {eth_sign}{eth_chg:.1f}%</div>
          </td>
        </tr>
      </table>
      <div style="font-size:12px;color:#86868b;margin-top:12px">ETH/BTC <span style="font-weight:600;color:#1d1d1f">{eth_btc:.6f}</span></div>
      <div style="margin-top:12px;display:flex;gap:8px">
        <span style="display:inline-block;padding:6px 14px;border-radius:20px;background:#f5f5f7;font-size:12px;color:#1d1d1f;font-weight:500">趋势 <b>{score}</b>/100 · {slabel}</span>
        <span style="display:inline-block;padding:6px 14px;border-radius:20px;background:#f5f5f7;font-size:12px;color:#1d1d1f;font-weight:500">恐贪 <b>{fng_val}</b> · {fng_tag}</span>
      </div>
    </div>"""

    # ═══ 恐贪仪表盘 ═══
    h += _vis_gauge(fng_val, fng_tag)

    # ═══ 一、AI 今日要点（最重要，放最前面）═══
    ai_summary = data.get("ai_summary", "")
    if ai_summary:
        h += '<div class="s"><p class="st" style="border-left-color:#007aff">AI 今日要点</p>'
        h += f'<div class="sb">{ai_summary.replace(chr(10), "<br>")}</div>'
        h += '</div>'

    # ═══ 交易策略指标（风险仪表盘上方）═══
    strategy = data.get("strategy_indicators", {})
    if strategy:
        h += _build_strategy_html(strategy, data.get("ai_strategy", ""))

    # ═══ 二、风险仪表盘（合并：衍生品+清算+多空+Gas）═══
    h += '<div class="s"><p class="st" style="border-left-color:#ff3b30">风险仪表盘</p>'

    # 资金费率热力图
    if funding:
        h += _vis_funding_heatmap(funding)

    # RSI 可视化进度条
    for sym, rsi in [("BTC", btc_rsi), ("ETH", eth_rsi)]:
        if rsi is not None:
            h += _vis_rsi_bar(rsi, sym)

    # 多空比（可视化进度条）
    if ls:
        h += '<div class="dv"></div>'
        for sym in ["BTC", "ETH"]:
            if sym in ls:
                lp = ls[sym]["long_pct"]
                tag = _ftag("多头拥挤", "r") if lp > 65 else _ftag("空头拥挤", "g") if lp < 35 else ""
                h += _vis_progress_bar(lp, sym)
                if tag:
                    h += f'<div style="text-align:right;margin-top:-6px;margin-bottom:4px">{tag}</div>'

    # 清算（合并到这里，只显示关键数据）
    if liq and liq.get("total_24h", 0) > 0:
        h += '<div class="dv"></div>'
        total = liq["total_24h"]
        long_pct = liq.get("long_ratio", 50)
        tag = _ftag("警告", "r") if total >= LIQUIDATION_ALERT else _ftag("偏高", "y") if total >= 100_000_000 else ""
        side = f"多{long_pct:.0f}%/空{100-long_pct:.0f}%"
        h += f'<div class="r"><span class="l">24h 清算</span><span class="v">{_mc(total)} ({side}) {tag}</span></div>'

    # Gas
    if gas and gas.get("standard"):
        tag = _ftag("拥堵", "r") if gas["fast"] > 50 else ""
        h += f'<div class="r"><span class="l">ETH Gas</span><span class="v">{gas["standard"]} Gwei {tag}</span></div>'

    # 逐币爆仓/持仓数据
    coin_liq = data.get("coin_liquidations", {})
    if coin_liq:
        h += '<div class="dv"></div>'
        for coin in ["BTC", "ETH"]:
            if coin not in coin_liq:
                continue
            cl = coin_liq[coin]
            oi_val = cl.get("oi_value_usd", 0)
            oi_chg = cl.get("oi_change_pct", 0)
            bsr = cl.get("buy_sell_ratio", 1)
            long_r = cl.get("long_ratio", 50)

            oi_tag = _ftag("OI飙升", "r") if oi_chg > 10 else _ftag("OI骤降", "b") if oi_chg < -10 else ""
            h += f'<div class="r"><span class="l">{coin} 未平仓</span><span class="v">{_mc(oi_val)} {_c(oi_chg)} {oi_tag}</span></div>'

            side_tag = _ftag("多头主导", "g") if bsr > 1.1 else _ftag("空头主导", "r") if bsr < 0.9 else ""
            h += f'<div class="r"><span class="l">{coin} 买卖比</span><span class="v">{bsr:.3f} (多{long_r:.0f}%/空{100-long_r:.0f}%) {side_tag}</span></div>'

    h += '</div>'

    # ═══ 期权交割日历 (含时间轴可视化) ═══
    options = data.get("options_expiry", {})
    if options:
        h += '<div class="s"><p class="st" style="border-left-color:#ff9500">期权交割日历</p>'
        for currency in ["BTC", "ETH"]:
            if currency not in options or not options[currency]:
                continue
            # 时间轴横条图
            h += _vis_timeline(options[currency], currency)
            # 详情行只显示重要项（<=7天或重大交割）
            for exp in options[currency]:
                days = exp["days_left"]
                if days > 7 and not exp["is_major"]:
                    continue
                tag = _ftag("重大交割", "r") if exp["is_major"] else ""
                if days <= 3:
                    tag += _ftag(f"⚠ {days}天后", "r")
                elif days <= 7:
                    tag += _ftag(f"{days}天后", "y")
                mp = exp.get("max_pain")
                mp_str = f" · MP {_p(mp)}" if mp else ""
                h += f'<div class="r"><span class="l">{currency} {exp["date_fmt"]}{mp_str}</span>'
                h += f'<span class="v">{_mc(exp["notional_usd"])} ({exp["oi_coins"]:,.0f}枚) {tag}</span></div>'
        h += '</div>'

    # ═══ 机构持仓 · 大额动向 (含比例条可视化) ═══
    holdings = data.get("institutional", {})
    if holdings:
        h += '<div class="s"><p class="st" style="border-left-color:#af52de">机构持仓 · 大额动向</p>'
        for sym in ["BTC", "ETH"]:
            if sym not in holdings:
                continue
            hd = holdings[sym]
            h += f'<div class="r"><span class="l">{sym} 机构总持仓</span><span class="v">{_mc(hd["total_value_usd"])}</span></div>'
            # 比例条可视化
            h += _vis_holdings_bars(hd["top_companies"], 5)
            for comp in hd["top_companies"][:5]:
                name = comp["name"]
                if len(name) > 18:
                    name = name[:16] + ".."
                val = comp["value_usd"]
                pct = comp["pct_supply"]
                h += f'<div class="r"><span class="l" style="padding-left:12px">{name}</span>'
                h += f'<span class="v">{_mc(val)} ({pct:.2f}%)</span></div>'
            h += '<div class="dv"></div>'
        h += '</div>'

    # ═══ 三、资金 & 宏观（合并：稳定币+市值+国债+汇率+TVL）═══
    h += '<div class="s"><p class="st" style="border-left-color:#34c759">资金 & 宏观</p>'

    # 稳定币（只显示有变动的）
    for sym in ["USDT", "USDC"]:
        if sym in stables:
            sc = stables[sym]
            h += f'<div class="r"><span class="l">{sym} 市值</span><span class="v">{_mc(sc["mcap"])} {_c(sc["mcap_change_pct"])}</span></div>'

    if gd:
        h += f'<div class="r"><span class="l">总市值</span><span class="v">{_mc(gd.get("total_market_cap", 0))}</span></div>'
        h += f'<div class="r"><span class="l">BTC 市占</span><span class="v">{gd.get("btc_dominance", 0):.1f}%</span></div>'

    # DeFi TVL
    if defi and defi.get("total_tvl"):
        h += f'<div class="r"><span class="l">DeFi TVL</span><span class="v">{_mc(defi["total_tvl"])} {_c(defi["change_pct"])}</span></div>'

    h += '<div class="dv"></div>'

    # 宏观指标
    if "US10Y" in yields:
        y = yields["US10Y"]
        h += f'<div class="r"><span class="l">US 10Y</span><span class="v">{y["value"]:.2f}% {_arrow(y["value"], y.get("prev"))}</span></div>'
    if "JP10Y" in yields:
        y = yields["JP10Y"]
        h += f'<div class="r"><span class="l">JP 10Y</span><span class="v">{y["value"]:.2f}% {_arrow(y["value"], y.get("prev"))}</span></div>'
    for pair in ["USD/JPY", "USD/CNY", "100JPY/CNY"]:
        if pair in forex:
            h += f'<div class="r"><span class="l">{pair}</span><span class="v">{forex[pair]:.2f}</span></div>'
    h += '</div>'

    # ═══ 四、行情 + 涨跌榜（合并）═══
    h += '<div class="s"><p class="st" style="border-left-color:#5856d6">行情一览</p>'

    # 涨跌榜标签先行
    by_change = sorted(prices.items(), key=lambda x: x[1]["change"], reverse=True)
    gainers = [(s, d_) for s, d_ in by_change[:3] if d_["change"] > 0]
    losers = [(s, d_) for s, d_ in by_change[-3:] if d_["change"] < 0]
    if gainers:
        tags = " ".join(_ftag(f'{s} +{d_["change"]:.1f}%', "g") for s, d_ in gainers)
        h += f'<p style="margin:0 0 8px;font-size:12px">Top {tags}</p>'
    if losers:
        tags = " ".join(_ftag(f'{s} {d_["change"]:.1f}%', "r") for s, d_ in losers)
        h += f'<p style="margin:0 0 8px;font-size:12px">Bottom {tags}</p>'

    # 价格表（去掉 BTC/ETH，Header 已展示）
    h += '<div class="dv"></div>'
    sorted_prices = sorted(prices.items(), key=lambda x: abs(x[1]["change"]), reverse=True)
    for sym, d_ in sorted_prices:
        if sym in ("BTC", "ETH"):
            continue
        h += f'<div class="r"><span class="l">{sym}</span><span class="v">{_p(d_["price"])} {_c(d_["change"])}</span></div>'
    h += '</div>'

    # ═══ 五、涨幅筛选 · 跑赢BTC (Binance) ═══
    screening = data.get("screening", {})
    if screening and screening.get("outperformers"):
        bn_count = screening.get("binance_count", 0)
        h += '<div class="s"><p class="st" style="border-left-color:#34c759">涨幅筛选 · 跑赢BTC</p>'

        bench = screening.get("btc_benchmark", {})
        bn_label = f" · Binance {bn_count}币" if bn_count else ""
        h += f'<div class="ab ab-i">BTC基准: 周 {bench.get("7d",0):+.1f}% · 月 {bench.get("30d",0):+.1f}% · 年 {bench.get("1y",0):+.1f}%{bn_label}</div>'

        period_labels = {"7d": "周涨幅", "30d": "月涨幅", "1y": "年涨幅"}
        for period, label in period_labels.items():
            ops = screening["outperformers"].get(period, [])
            if not ops:
                continue
            # 只看 Binance 上市的，分前200和200后
            bn_ops = [c for c in ops if c.get("binance", True)]
            top200 = [c for c in bn_ops if c["rank"] <= 200]
            after200 = [c for c in bn_ops if c["rank"] > 200]

            h += '<div class="dv"></div>'
            h += f'<p style="font-size:11px;color:#86868b;margin:8px 0 4px;font-weight:600">{label} · 前200 ({len(top200)}个)</p>'
            # 条形图可视化
            h += _vis_bar_chart(top200[:5], "vs_btc", "symbol", 5)
            for coin in top200[:3]:
                h += f'<div class="r"><span class="l">#{coin["rank"]} {coin["symbol"]}</span>'
                h += f'<span class="v">{coin["change"]:+.1f}% <span style="font-size:10px;color:#34a853">+{coin["vs_btc"]:.1f}%</span></span></div>'
            if len(top200) > 3:
                h += f'<p style="font-size:10px;color:#c7c7cc;text-align:center">...及其余 {len(top200)-3} 个</p>'

            if after200:
                h += '<div class="dv"></div>'
                h += f'<p style="font-size:11px;color:#86868b;margin:8px 0 4px;font-weight:600">{label} · 200名后 ({len(after200)}个)</p>'
                for coin in after200[:3]:
                    h += f'<div class="r"><span class="l">#{coin["rank"]} {coin["symbol"]}</span>'
                    h += f'<span class="v">{coin["change"]:+.1f}% <span style="font-size:10px;color:#34a853">+{coin["vs_btc"]:.1f}%</span></span></div>'
                if len(after200) > 3:
                    h += f'<p style="font-size:10px;color:#c7c7cc;text-align:center">...及其余 {len(after200)-3} 个</p>'

        h += '</div>'

    # ═══ 关注币种动态 ═══
    watchlist_news = data.get("watchlist_news", {})
    if watchlist_news:
        h += '<div class="s"><p class="st" style="border-left-color:#ff9500">关注币种动态</p>'
        for sym, news_list in watchlist_news.items():
            for n in news_list[:2]:  # 每币最多2条
                title = n.get("title_cn", n["title"])
                source = n.get("source", "")
                link = n.get("link", "")
                h += '<div class="ni">'
                if link:
                    h += f'<a href="{link}">{sym} · {title}</a>'
                else:
                    h += f'{sym} · {title}'
                if source:
                    h += f'<span class="sm">{source}</span>'
                h += '</div>'
        h += '</div>'

    # ═══ 六、新闻 + 决策参考（合并）═══
    h += '<div class="s"><p class="st" style="border-left-color:#ff9500">新闻 & 研判</p>'

    # 决策参考放前面（最重要）
    summary = _generate_summary(data)
    h += f'<div class="sb">{summary}</div>'

    # 新闻列表
    if news:
        for item in news[:6]:
            title = item.get("title_cn", item["title"])
            link = item.get("link", "")
            source = item.get("source", "")
            urgent_tag = _ftag("重要", "r") if item.get("urgent") else ""
            # 重要新闻加浅红高亮背景
            ni_style = ' style="background:#fff2f1;border-left-color:#ff3b30"' if item.get("urgent") else ""
            h += f'<div class="ni"{ni_style}>'
            if link:
                h += f'<a href="{link}">{title}</a>{urgent_tag}'
            else:
                h += f'{title}{urgent_tag}'
            if source:
                h += f'<span class="sm" style="display:inline-block;padding:2px 8px;border-radius:4px;background:#e5e5ea;color:#636366;margin-top:4px">{source}</span>'
            h += '</div>'
    h += '</div>'

    # Footer
    h += f'<div class="ft">Powered by <span>Automated Intelligence</span> · {d}</div>'
    h += '</div></body></html>'
    return h


def _generate_summary(data: dict) -> str:
    """根据指标自动生成决策摘要"""
    signals = []
    fng = data.get("fng", {})
    prices = data.get("prices", {})
    funding = data.get("funding", {})
    stables = data.get("stablecoins", {})
    btc_rsi = data.get("btc_rsi")
    yields_ = data.get("yields", {})

    # 恐贪
    fng_val = fng.get("value", 50)
    if fng_val <= 20:
        signals.append("恐贪指数极度恐惧，历史上常为逆向建仓区间")
    elif fng_val <= 35:
        signals.append("市场偏恐惧，可关注逢低机会")
    elif fng_val >= 80:
        signals.append("市场极度贪婪，注意仓位与止盈")
    elif fng_val >= 65:
        signals.append("市场偏贪婪，谨慎追高")

    # RSI
    if btc_rsi is not None:
        if btc_rsi >= RSI_OVERBOUGHT:
            signals.append(f"BTC RSI {btc_rsi:.0f} 超买，短期回调风险增加")
        elif btc_rsi <= RSI_OVERSOLD:
            signals.append(f"BTC RSI {btc_rsi:.0f} 超卖，可能接近阶段底部")

    # 资金费率
    if funding:
        avg = sum(funding.values()) / len(funding)
        if avg > FUNDING_HOT:
            signals.append("资金费率偏高，多头拥挤，注意杠杆风险")
        elif avg < FUNDING_COLD:
            signals.append("资金费率为负，空头占优，可能处于洗盘阶段")

    # 稳定币
    usdt = stables.get("USDT", {})
    if usdt.get("mcap_change_pct", 0) > 0.5:
        signals.append("USDT 市值增长，场外资金流入积极")
    elif usdt.get("mcap_change_pct", 0) < -0.3:
        signals.append("USDT 市值缩水，场外资金流出需关注")

    # 美债
    us10y = yields_.get("US10Y", {})
    if us10y.get("value", 0) > 5.0:
        signals.append("美债收益率高位运行，风险资产承压")
    elif us10y.get("value", 0) and us10y.get("prev"):
        diff = us10y["value"] - us10y["prev"]
        if diff > 0.1:
            signals.append("美债收益率上行，流动性收紧预期")
        elif diff < -0.1:
            signals.append("美债收益率回落，流动性环境改善")

    # 清算
    liq = data.get("liquidations", {})
    if liq.get("total_24h", 0) >= LIQUIDATION_ALERT:
        long_pct = liq.get("long_ratio", 50)
        side = "多头" if long_pct > 60 else "空头" if long_pct < 40 else "多空"
        signals.append(f"24h 清算 {_mc(liq['total_24h'])}，{side}为主，杠杆风险释放中")

    # BTC
    btc = prices.get("BTC", {})
    if btc.get("change", 0) > 5:
        signals.append(f"BTC 24h +{btc['change']:.1f}%，短期动能强劲")
    elif btc.get("change", 0) < -5:
        signals.append(f"BTC 24h {btc['change']:.1f}%，注意风控")

    if not signals:
        signals.append("各项指标正常区间，建议维持现有策略")

    return "<br>".join(f"· {s}" for s in signals)


# ══════════════════════════════════════════════════════════════════
#  即时预警 (Trigger Alerts)
# ══════════════════════════════════════════════════════════════════

def build_alert_html(alerts: list[dict]) -> str:
    now = datetime.now(CST)
    ts = now.strftime("%Y-%m-%d %H:%M")

    h = f'<!DOCTYPE html><html><head><meta charset="utf-8">{STYLE}</head><body><div class="c">'
    h += f'<div style="height:4px;background:linear-gradient(90deg,#ff3b30,#ff9500)"></div>'
    h += f'<div class="hd"><p class="sub">TRIGGER ALERT</p><h1>Alert</h1><p class="t">{ts} CST</p></div>'

    for section in alerts:
        h += f'<div class="s"><p class="st" style="border-left-color:#ff3b30">{section["title"]}</p>'
        for item in section["items"]:
            cls = "ab-d" if section.get("danger") else "ab-i"
            h += f'<div class="ab {cls}">{item}</div>'
        h += '</div>'

    h += f'<div class="ft">Powered by <span>Automated Intelligence</span> · {ts}</div>'
    h += '</div></body></html>'
    return h


# ══════════════════════════════════════════════════════════════════
#  推送
# ══════════════════════════════════════════════════════════════════

def _convert_links_for_wechat(html_body: str) -> str:
    """将 <a href="url">title</a> 转为微信可读格式：标题 + 可复制链接"""
    def _replace_link(m):
        url = m.group(1)
        text = m.group(2)
        # 短链接显示
        short = url.split("//")[-1]
        if len(short) > 50:
            short = short[:47] + "..."
        return f'{text}<br><span style="font-size:10px;color:#4285f4;word-break:break-all">{url}</span>'
    return re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', _replace_link, html_body, flags=re.DOTALL)


def _trim_html_for_wechat(html_body: str, max_len: int = 18000) -> str:
    """裁剪 HTML 内容以适应 PushPlus 2万字限制"""
    # 先转换链接为可复制文本
    html_body = _convert_links_for_wechat(html_body)
    if len(html_body) <= max_len:
        return html_body
    # 移除涨幅筛选（最占篇幅的部分）
    trimmed = re.sub(
        r'<div class="s"><p class="st">涨幅筛选.*?</div>\s*(?=<div class="s">|<div class="ft">)',
        '', html_body, flags=re.DOTALL,
    )
    if len(trimmed) <= max_len:
        return trimmed
    # 还超？移除机构持仓
    trimmed = re.sub(
        r'<div class="s"><p class="st">机构持仓.*?</div>\s*(?=<div class="s">|<div class="ft">)',
        '', trimmed, flags=re.DOTALL,
    )
    if len(trimmed) <= max_len:
        return trimmed
    # 最后手段：截断
    cut = trimmed[:max_len]
    close_idx = cut.rfind('</div>')
    if close_idx > 0:
        cut = cut[:close_idx + 6]
    cut += '<div class="ft">内容已裁剪，完整版请查看邮件</div></div></body></html>'
    return cut


def push_wechat(title: str, html_body: str):
    for token in PUSHPLUS_TOKENS:
        token = token.strip()
        if not token:
            continue
        content = _trim_html_for_wechat(html_body)
        payload = json.dumps({
            "token": token, "title": title,
            "content": content, "template": "html",
        }).encode("utf-8")
        req = Request("http://www.pushplus.plus/send", data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                if result.get("code") == 200:
                    print(f"[OK] 微信推送: token={token[:8]}...")
                else:
                    print(f"[WARN] 微信异常: {result}")
        except (URLError, OSError) as e:
            print(f"[ERROR] 微信失败: {e}")


def send_email(subject: str, html_body: str):
    if not SMTP_USER or not SMTP_PASS or not EMAIL_TO:
        print("[SKIP] 邮件未配置")
        return
    recipients = [addr.strip() for addr in EMAIL_TO.split(",") if addr.strip()]
    if not recipients:
        print("[SKIP] 无有效收件人")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
        print(f"[OK] 邮件已发送: {', '.join(recipients)}")
    except Exception as e:
        print(f"[ERROR] 邮件失败: {e}")


def push_all(title: str, html_body: str):
    push_wechat(title, html_body)
    send_email(title, html_body)


# ══════════════════════════════════════════════════════════════════
#  主逻辑
# ══════════════════════════════════════════════════════════════════

def run_daily():
    today = datetime.now(CST).strftime("%Y-%m-%d")
    print("[INFO] === 每日晨报 ===")

    print("[INFO] 获取数据...")
    prices = fetch_prices()
    fng = fetch_fear_greed()
    news = fetch_news()

    data = {
        "prices": prices,
        "stablecoins": fetch_stablecoin_mcap(),
        "forex": fetch_forex(),
        "fng": fng,
        "global": fetch_global_data(),
        "funding": fetch_funding_rates(),
        "yields": fetch_macro_yields(),
        "btc_rsi": fetch_rsi("bitcoin"),
        "eth_rsi": fetch_rsi("ethereum"),
        "liquidations": fetch_liquidations(),
        "long_short": fetch_long_short_ratio(),
        "gas_fee": fetch_gas_fee(),
        "defi_tvl": fetch_defi_tvl(),
        "news": news,
        "ai_summary": generate_ai_summary(news, prices, fng),
        "options_expiry": _safe_fetch(fetch_options_expiry, {}),
        "coin_liquidations": _safe_fetch(fetch_coin_liquidations, {}),
        "screening": _safe_fetch(fetch_top200_vs_btc, {}),
        "institutional": _safe_fetch(fetch_institutional_holdings, {}),
        "strategy_indicators": _safe_fetch(fetch_strategy_indicators, {}),
        "watchlist_news": _safe_fetch(fetch_watchlist_news, {}),
    }

    # 趋势评分
    data["trend_score"] = calculate_trend_score(data)

    # AI 策略分析
    data["ai_strategy"] = generate_ai_strategy(
        data.get("strategy_indicators", {}),
        fng, data.get("funding", {}),
    )

    liq_total = data["liquidations"].get("total_24h", 0)
    screening = data.get("screening", {})
    ops_count = sum(len(v) for v in screening.get("outperformers", {}).values())
    opt_btc = len(data.get("options_expiry", {}).get("BTC", []))
    print(f"[INFO] 币价:{len(data['prices'])} 费率:{len(data['funding'])} "
          f"宏观:{len(data['yields'])} 清算:{_mc(liq_total)} "
          f"多空:{len(data['long_short'])} Gas:{data['gas_fee'].get('standard', '?')} "
          f"TVL:{_mc(data['defi_tvl'].get('total_tvl', 0))} "
          f"趋势:{data['trend_score']} 新闻:{len(data['news'])} "
          f"期权到期:{opt_btc} 跑赢BTC:{ops_count}个 "
          f"策略:{len(data.get('strategy_indicators', {}))}币")

    html = build_daily_html(data)
    push_all(f"{today} Market Digest", html)

    # 归档快照
    archive_snapshot(data)


def run_alert():
    print("[INFO] === 即时预警 ===")

    prices = fetch_prices()
    fng = fetch_fear_greed()
    funding = fetch_funding_rates()
    btc_rsi = fetch_rsi("bitcoin")
    eth_rsi = fetch_rsi("ethereum")

    sections = []

    # 价格突破
    price_msgs = []
    for sym, th in PRICE_ALERTS.items():
        if sym not in prices:
            continue
        p = prices[sym]["price"]
        if p >= th["above"]:
            price_msgs.append(f"{sym} 突破 ${th['above']:,} → 当前 {_p(p)}")
        elif p <= th["below"]:
            price_msgs.append(f"{sym} 跌破 ${th['below']:,} → 当前 {_p(p)}")
    if price_msgs:
        sections.append({"title": "价格突破", "items": price_msgs, "danger": True})

    # 异动 ±10%
    pump_msgs = []
    for sym, d in prices.items():
        if abs(d["change"]) >= PUMP_THRESHOLD:
            direction = "暴涨" if d["change"] > 0 else "暴跌"
            sign = "+" if d["change"] > 0 else ""
            pump_msgs.append(f"{sym} {direction} {sign}{d['change']:.1f}% → {_p(d['price'])}")
    if pump_msgs:
        sections.append({"title": "异动币种 (24h ±10%+)", "items": pump_msgs, "danger": True})

    # 恐贪极端
    fng_val = fng.get("value", 50)
    if fng_val <= FNG_EXTREME_FEAR:
        sections.append({"title": "情绪异常", "items": [
            f"恐慌贪婪指数 {fng_val}（极度恐慌），可作为逆向参考"
        ]})

    # RSI 极端
    rsi_msgs = []
    if btc_rsi is not None:
        if btc_rsi >= RSI_OVERBOUGHT:
            rsi_msgs.append(f"BTC RSI {btc_rsi:.0f} 进入超买区间")
        elif btc_rsi <= RSI_OVERSOLD:
            rsi_msgs.append(f"BTC RSI {btc_rsi:.0f} 进入超卖区间")
    if eth_rsi is not None:
        if eth_rsi >= RSI_OVERBOUGHT:
            rsi_msgs.append(f"ETH RSI {eth_rsi:.0f} 进入超买区间")
        elif eth_rsi <= RSI_OVERSOLD:
            rsi_msgs.append(f"ETH RSI {eth_rsi:.0f} 进入超卖区间")
    if rsi_msgs:
        sections.append({"title": "RSI 极端", "items": rsi_msgs})

    # 大额清算
    liq = fetch_liquidations()
    if liq.get("total_24h", 0) >= LIQUIDATION_ALERT:
        total = liq["total_24h"]
        long_pct = liq.get("long_ratio", 50)
        side = "多头" if long_pct > 60 else "空头" if long_pct < 40 else "多空均衡"
        sections.append({"title": "大额清算", "items": [
            f"24h 清算 {_mc(total)}，{side}清算占比 {long_pct:.0f}%"
        ], "danger": True})

    # 资金费率异常
    fund_msgs = []
    for sym, rate in funding.items():
        if rate > FUNDING_HOT:
            fund_msgs.append(f"{sym} 资金费率 {rate:.4f}% 过热")
        elif rate < FUNDING_COLD:
            fund_msgs.append(f"{sym} 资金费率 {rate:.4f}% 为负")
    if fund_msgs:
        sections.append({"title": "资金费率异常", "items": fund_msgs, "danger": True})

    # Gas 费飙升
    gas = fetch_gas_fee()
    if gas and gas.get("fast", 0) > 100:
        sections.append({"title": "Gas Fee 异常", "items": [
            f"ETH Gas 飙升: {gas['low']}/{gas['standard']}/{gas['fast']} Gwei (低/中/快)"
        ], "danger": True})

    if sections:
        count = sum(len(s["items"]) for s in sections)
        print(f"[ALERT] 推送 {count} 条预警")
        html = build_alert_html(sections)
        push_all("Alert", html)
    else:
        print("[INFO] 无预警触发")


def run_weekly():
    """周报：涨幅筛选（全量展示） + 期权交割 + 市场总结"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    print("[INFO] === 周报 ===")

    prices = fetch_prices()
    fng = fetch_fear_greed()
    gd = fetch_global_data()
    funding = fetch_funding_rates()
    screening = _safe_fetch(fetch_top200_vs_btc, {})
    options = _safe_fetch(fetch_options_expiry, {})
    coin_liq = _safe_fetch(fetch_coin_liquidations, {})
    institutional = _safe_fetch(fetch_institutional_holdings, {})
    strategy = _safe_fetch(fetch_strategy_indicators, {})
    ai_strategy = generate_ai_strategy(strategy, fng, funding)

    # 构建周报 HTML
    now = datetime.now(CST)
    d, t = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")

    h = f'<!DOCTYPE html><html><head><meta charset="utf-8">{STYLE}</head><body><div class="c">'
    h += f"""<div class="hd">
      <p class="sub">WEEKLY REPORT</p>
      <h1>周报 · Performance Review</h1>
      <p class="t">{d} · {t} CST</p>
    </div>"""

    # 市场概览
    btc = prices.get("BTC", {})
    eth = prices.get("ETH", {})
    h += '<div class="s"><p class="st" style="border-left-color:#5856d6">市场概览</p>'
    h += f'<div class="r"><span class="l">BTC</span><span class="v">{_p(btc.get("price", 0))} {_c(btc.get("change", 0))}</span></div>'
    h += f'<div class="r"><span class="l">ETH</span><span class="v">{_p(eth.get("price", 0))} {_c(eth.get("change", 0))}</span></div>'
    fng_val = fng.get("value", 0)
    h += f'<div class="r"><span class="l">恐贪指数</span><span class="v">{fng_val} · {fng.get("label", "")}</span></div>'
    if gd:
        h += f'<div class="r"><span class="l">总市值</span><span class="v">{_mc(gd.get("total_market_cap", 0))}</span></div>'
        h += f'<div class="r"><span class="l">BTC 市占</span><span class="v">{gd.get("btc_dominance", 0):.1f}%</span></div>'
    h += '</div>'

    # 期权交割日历（含时间轴可视化）
    if options:
        h += '<div class="s"><p class="st" style="border-left-color:#ff9500">期权交割日历</p>'
        for currency in ["BTC", "ETH"]:
            if currency not in options or not options[currency]:
                continue
            h += _vis_timeline(options[currency], currency)
            for exp in options[currency]:
                days = exp["days_left"]
                tag = _ftag("重大交割", "r") if exp["is_major"] else ""
                if days <= 3:
                    tag += _ftag(f"⚠ {days}天后", "r")
                elif days <= 7:
                    tag += _ftag(f"{days}天后", "y")
                mp = exp.get("max_pain")
                mp_str = f" · MP {_p(mp)}" if mp else ""
                h += f'<div class="r"><span class="l">{currency} {exp["date_fmt"]}{mp_str}</span>'
                h += f'<span class="v">{_mc(exp["notional_usd"])} ({exp["oi_coins"]:,.0f}枚) {tag}</span></div>'
        h += '</div>'

    # BTC/ETH 逐币持仓
    if coin_liq:
        h += '<div class="s"><p class="st" style="border-left-color:#ff3b30">BTC/ETH 衍生品持仓</p>'
        for coin in ["BTC", "ETH"]:
            if coin not in coin_liq:
                continue
            cl = coin_liq[coin]
            oi_val = cl.get("oi_value_usd", 0)
            oi_chg = cl.get("oi_change_pct", 0)
            bsr = cl.get("buy_sell_ratio", 1)
            long_r = cl.get("long_ratio", 50)
            h += f'<div class="r"><span class="l">{coin} 未平仓</span><span class="v">{_mc(oi_val)} {_c(oi_chg)}</span></div>'
            h += f'<div class="r"><span class="l">{coin} 多空</span><span class="v">买卖比 {bsr:.3f} · 多{long_r:.0f}%/空{100-long_r:.0f}%</span></div>'
            h += '<div class="dv"></div>'
        h += '</div>'

    # 机构持仓
    if institutional:
        h += '<div class="s"><p class="st" style="border-left-color:#af52de">机构持仓 · 大额动向</p>'
        for sym in ["BTC", "ETH"]:
            if sym not in institutional:
                continue
            hd = institutional[sym]
            h += f'<div class="r"><span class="l">{sym} 机构总持仓</span><span class="v">{_mc(hd["total_value_usd"])}</span></div>'
            for comp in hd["top_companies"][:5]:
                name = comp["name"]
                if len(name) > 18:
                    name = name[:16] + ".."
                h += f'<div class="r"><span class="l" style="padding-left:12px">{name}</span>'
                h += f'<span class="v">{_mc(comp["value_usd"])} ({comp["pct_supply"]:.2f}%)</span></div>'
            h += '<div class="dv"></div>'
        h += '</div>'

    # 交易策略指标 + AI 分析
    if strategy:
        h += _build_strategy_html(strategy, ai_strategy)

    # 涨幅筛选（全量展示，周报核心内容）
    if screening and screening.get("outperformers"):
        h += '<div class="s"><p class="st" style="border-left-color:#34c759">涨幅筛选 · 跑赢BTC (全量)</p>'

        bench = screening.get("btc_benchmark", {})
        h += f'<div class="ab ab-i">BTC基准: 周 {bench.get("7d",0):+.1f}% · 月 {bench.get("30d",0):+.1f}% · 年 {bench.get("1y",0):+.1f}% &nbsp;(市值前{screening.get("total_coins", 200)})</div>'

        period_labels = {"7d": "周涨幅", "30d": "月涨幅", "1y": "年涨幅"}
        for period, label in period_labels.items():
            ops = screening["outperformers"].get(period, [])
            if not ops:
                continue
            h += '<div class="dv"></div>'
            h += f'<p style="font-size:11px;color:#8e8e93;margin:8px 0 4px;font-weight:600">{label} 跑赢BTC ({len(ops)}个)</p>'
            for coin in ops[:20]:  # 周报展示 top 20
                h += f'<div class="r"><span class="l">#{coin["rank"]} {coin["symbol"]}</span>'
                h += f'<span class="v">{coin["change"]:+.1f}% <span style="font-size:10px;color:#34a853">+{coin["vs_btc"]:.1f}%</span></span></div>'
            if len(ops) > 20:
                h += f'<p style="font-size:10px;color:#c7c7cc;text-align:center">...及其余 {len(ops)-20} 个币种</p>'

        h += '</div>'

    h += f'<div class="ft">Powered by <span>Automated Intelligence</span> · {d}</div>'
    h += '</div></body></html>'

    push_all(f"{today} 周报 · Weekly Report", h)


def run_urgent():
    """紧急新闻检查：AI 过滤 + 关注币种 + 价格异动"""
    print("[INFO] === 紧急新闻检查 ===")
    news = fetch_news()
    urgent_news = [n for n in news if n.get("urgent")]

    # AI 智能过滤：只保留真正重大事件
    if urgent_news:
        urgent_news = _ai_filter_urgent_news(urgent_news)

    prices = fetch_prices()

    sections = []

    # 紧急新闻（AI 过滤后）
    if urgent_news:
        sections.append({
            "title": f"紧急新闻 ({len(urgent_news)}条)",
            "items": [n.get("title_cn", n["title"]) for n in urgent_news[:5]],
            "danger": True,
        })

    # 价格异动
    pump_msgs = []
    for sym, d in prices.items():
        if abs(d["change"]) >= PUMP_THRESHOLD:
            direction = "暴涨" if d["change"] > 0 else "暴跌"
            pump_msgs.append(f'{sym} {direction} {d["change"]:+.1f}% → {_p(d["price"])}')
    if pump_msgs:
        sections.append({"title": "价格异动 (24h ±10%+)", "items": pump_msgs, "danger": True})

    # 关注币种重要新闻
    watchlist_news = fetch_watchlist_news()
    if watchlist_news:
        wl_items = []
        for sym, news_list in watchlist_news.items():
            for n in news_list[:2]:
                wl_items.append(f"{sym}: {n.get('title_cn', n['title'])}")
        if wl_items:
            sections.append({
                "title": f"关注币种动态 ({len(wl_items)}条)",
                "items": wl_items,
            })

    if sections:
        count = sum(len(s["items"]) for s in sections)
        print(f"[URGENT] 推送 {count} 条紧急消息")
        html = build_alert_html(sections)
        push_all("URGENT", html)
    else:
        print("[INFO] 无紧急事件")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    modes = {
        "daily": run_daily,
        "alert": run_alert,
        "weekly": run_weekly,
        "urgent": run_urgent,
    }
    if mode in modes:
        modes[mode]()
    else:
        print(f"[ERROR] 未知模式: {mode} (可用: {'/'.join(modes)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
