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

STABLECOINS = {"tether": "USDT", "usd-coin": "USDC"}

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


# ══════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════

def fetch_json(url: str, timeout: int = 30):
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


# ══════════════════════════════════════════════════════════════════
#  数据获取层
# ══════════════════════════════════════════════════════════════════

def fetch_prices() -> dict:
    ids = ",".join(TRACKED_COINS.keys())
    url = f"{COINGECKO}/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    data = fetch_json(url)
    if not data:
        return {}
    result = {}
    for coin_id, symbol in TRACKED_COINS.items():
        if coin_id in data:
            result[symbol] = {
                "price": data[coin_id]["usd"],
                "change": data[coin_id].get("usd_24h_change", 0) or 0,
            }
    return result


def fetch_stablecoin_mcap() -> dict:
    ids = ",".join(STABLECOINS.keys())
    url = f"{COINGECKO}/coins/markets?vs_currency=usd&ids={ids}&price_change_percentage=24h"
    data = fetch_json(url)
    if not data:
        return {}
    result = {}
    for coin in data:
        symbol = STABLECOINS.get(coin["id"], coin["symbol"].upper())
        result[symbol] = {
            "mcap": coin.get("market_cap", 0),
            "mcap_change_pct": coin.get("market_cap_change_percentage_24h", 0) or 0,
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
    if not data or "data" not in data:
        return {}
    gd = data["data"]
    return {
        "btc_dominance": gd["market_cap_percentage"].get("btc", 0),
        "eth_dominance": gd["market_cap_percentage"].get("eth", 0),
        "total_market_cap": gd["total_market_cap"].get("usd", 0),
        "total_volume": gd["total_volume"].get("usd", 0),
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

def fetch_macro_yields() -> dict:
    """获取美国10年期国债 + 日本10年期国债收益率"""
    result = {}

    # US 10Y - FRED API (DEMO_KEY 有限额但够用)
    us_data = fetch_json(
        "https://api.stlouisfed.org/fred/series/observations"
        "?series_id=DGS10&api_key=DEMO_KEY&file_type=json"
        "&sort_order=desc&limit=2"
    )
    if us_data and "observations" in us_data:
        obs = [o for o in us_data["observations"] if o["value"] != "."]
        if len(obs) >= 2:
            result["US10Y"] = {"value": float(obs[0]["value"]),
                               "prev": float(obs[1]["value"])}
        elif len(obs) == 1:
            result["US10Y"] = {"value": float(obs[0]["value"]), "prev": None}

    # JP 10Y - FRED series: IRLTLT01JPM156N (月度) 太慢
    # 用 investing.com 不现实，改用 FRED 的日本长期利率
    jp_data = fetch_json(
        "https://api.stlouisfed.org/fred/series/observations"
        "?series_id=IRLTLT01JPM156N&api_key=DEMO_KEY&file_type=json"
        "&sort_order=desc&limit=2"
    )
    if jp_data and "observations" in jp_data:
        obs = [o for o in jp_data["observations"] if o["value"] != "."]
        if len(obs) >= 2:
            result["JP10Y"] = {"value": float(obs[0]["value"]),
                               "prev": float(obs[1]["value"])}
        elif len(obs) == 1:
            result["JP10Y"] = {"value": float(obs[0]["value"]), "prev": None}

    return result


def fetch_forex() -> dict:
    """获取 USD/JPY, USD/CNY 汇率及变动方向"""
    data = fetch_json("https://open.er-api.com/v6/latest/USD")
    if not data or not data.get("rates"):
        return {}
    rates = data["rates"]
    result = {}
    for pair, code in [("USD/JPY", "JPY"), ("USD/CNY", "CNY")]:
        if code in rates:
            result[pair] = rates[code]
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
    if not data or "prices" not in data:
        return None
    return calculate_rsi([p[1] for p in data["prices"]])


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

def fetch_options_expiry() -> dict:
    """获取 BTC/ETH 期权到期日及未平仓量 (Deribit 公开 API)"""
    result = {}
    for currency in ["BTC", "ETH"]:
        url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
        data = fetch_json(url)
        if not data or "result" not in data:
            continue

        # 按到期日汇总未平仓量
        expiry_oi = {}
        for item in data["result"]:
            name = item.get("instrument_name", "")
            oi = float(item.get("open_interest", 0))
            underlying = float(item.get("underlying_price", 0))
            if oi <= 0:
                continue
            parts = name.split("-")
            if len(parts) >= 2:
                expiry_str = parts[1]
                if expiry_str not in expiry_oi:
                    expiry_oi[expiry_str] = {"oi_coins": 0, "underlying": underlying}
                expiry_oi[expiry_str]["oi_coins"] += oi

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
            expiries.append({
                "date": exp_str,
                "date_fmt": exp_date.strftime("%Y-%m-%d"),
                "days_left": days_left,
                "oi_coins": info["oi_coins"],
                "notional_usd": notional,
                "is_major": notional >= 1_000_000_000,
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
    return result


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
        return {}

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
        return "Strong Bull", "g"
    elif score >= 60:
        return "Bullish", "g"
    elif score >= 45:
        return "Neutral", "b"
    elif score >= 30:
        return "Bearish", "y"
    else:
        return "Strong Bear", "r"


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

def generate_ai_summary(news: list[dict], prices: dict, fng: dict) -> str:
    """用 Groq (Llama 3) 把新闻浓缩成 3 句话的今日要点"""
    if not GROQ_API_KEY:
        print("[SKIP] GROQ_API_KEY 未配置，跳过 AI 摘要")
        return ""

    # 构建新闻标题列表
    titles = [item.get("title_cn", item["title"]) for item in news[:15]]
    titles_text = "\n".join(f"- {t}" for t in titles)

    # 市场上下文
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

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 300,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            text = result["choices"][0]["message"]["content"]
            print(f"[OK] AI 摘要生成完成 ({len(text)} 字)")
            return text
    except Exception as e:
        print(f"[ERROR] AI 摘要失败: {e}")
        return ""


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


# ══════════════════════════════════════════════════════════════════
#  Apple 风格极简 HTML 模板
# ══════════════════════════════════════════════════════════════════

STYLE = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:-apple-system,'SF Pro Display','Helvetica Neue','PingFang SC',sans-serif;
  background:linear-gradient(170deg,#faf9f6 0%,#f5f0e8 100%);
  color:#1d1d1f;padding:24px 16px;
  -webkit-font-smoothing:antialiased
}
.c{
  max-width:560px;margin:0 auto;
  background:rgba(255,255,255,0.65);
  backdrop-filter:blur(40px) saturate(180%);
  -webkit-backdrop-filter:blur(40px) saturate(180%);
  border-radius:24px;overflow:hidden;
  border:1px solid rgba(255,255,255,0.7);
  box-shadow:0 8px 40px rgba(0,0,0,0.06),0 1px 3px rgba(0,0,0,0.04)
}
.hd{
  padding:36px 32px 20px;
  background:rgba(255,252,245,0.5);
  border-bottom:1px solid rgba(0,0,0,0.04);
  color:#1d1d1f
}
.hd h1{font-size:22px;font-weight:700;letter-spacing:-.5px;margin-bottom:4px;color:#1a1a1a}
.hd .sub{font-size:11px;color:#999;font-weight:400;letter-spacing:1.5px;text-transform:uppercase}
.hd .t{font-size:12px;color:#888;margin-top:8px;font-variant-numeric:tabular-nums}
.s{padding:24px 32px;border-top:1px solid rgba(0,0,0,0.04)}
.st{
  font-size:10px;font-weight:600;color:#b0a898;
  text-transform:uppercase;letter-spacing:1.5px;
  margin-bottom:14px;
  display:flex;align-items:center;gap:6px
}
.st::before{
  content:'';display:inline-block;width:3px;height:12px;
  border-radius:2px;background:linear-gradient(180deg,#c9b99a,#a89880)
}
.r{
  display:flex;justify-content:space-between;align-items:center;
  padding:8px 0;font-size:13px;line-height:1.4
}
.r .l{color:#6e6e73;font-weight:400}
.r .v{font-weight:600;font-variant-numeric:tabular-nums;text-align:right;letter-spacing:-.2px;color:#1d1d1f}
.up{color:#34a853}.dn{color:#ea4335}.nt{color:#b0b0b0}
.tg{
  display:inline-block;font-size:9px;font-weight:600;
  padding:3px 8px;border-radius:6px;margin-left:6px;
  letter-spacing:.3px;text-transform:uppercase
}
.tg-r{background:rgba(234,67,53,0.07);color:#ea4335}
.tg-b{background:rgba(66,133,244,0.07);color:#4285f4}
.tg-g{background:rgba(52,168,83,0.07);color:#34a853}
.tg-y{background:rgba(205,170,110,0.1);color:#b8960c}
.dv{height:1px;background:rgba(0,0,0,0.04);margin:6px 0}
.ab{
  margin:8px 0;padding:14px 16px;border-radius:14px;
  font-size:12px;line-height:1.6
}
.ab-d{background:rgba(234,67,53,0.04);border:1px solid rgba(234,67,53,0.1)}
.ab-i{background:rgba(201,185,154,0.08);border:1px solid rgba(201,185,154,0.15)}
.sb{
  background:rgba(250,248,242,0.6);
  border:1px solid rgba(201,185,154,0.15);
  border-radius:14px;padding:16px 18px;margin-top:10px;
  font-size:12px;line-height:1.8;color:#48484a
}
.ni{
  padding:12px 16px;margin:8px 0;font-size:12px;line-height:1.6;
  background:rgba(250,248,242,0.5);border-radius:12px;
  border-left:3px solid rgba(201,185,154,0.4)
}
.ni a{color:#1d1d1f;text-decoration:none;font-weight:500}
.ni a:hover{text-decoration:underline}
.ni .sm{color:#999;font-size:11px;margin-top:2px;display:block}
.ft{
  padding:20px 32px;text-align:center;
  font-size:10px;color:#c7c2b8;letter-spacing:.3px;
  border-top:1px solid rgba(0,0,0,0.03)
}
.ft span{color:#b0a898;font-weight:600}
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
    sign = "+" if change >= 0 else ""
    cls = "up" if change >= 0 else "dn"
    return f'<span class="{cls}">{sign}{change:.1f}%</span>'


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
        fng_tag = "Extreme Fear"
    elif fng_val <= 45:
        fng_tag = "Fear"
    elif fng_val <= 55:
        fng_tag = "Neutral"
    elif fng_val <= 75:
        fng_tag = "Greed"
    else:
        fng_tag = "Extreme Greed"

    h += f"""<div class="hd">
      <p class="sub">DAILY BRIEFING</p>
      <h1>Market Digest</h1>
      <p class="t">{d} · {t} CST</p>
      <table style="width:100%;margin-top:16px;color:#1d1d1f;font-size:13px;border-collapse:collapse">
        <tr>
          <td style="padding:6px 0"><b>BTC</b></td>
          <td style="text-align:right">{_p(btc.get('price', 0))}</td>
          <td style="text-align:right;width:70px;opacity:0.8">{'+' if btc.get('change', 0) >= 0 else ''}{btc.get('change', 0):.1f}%</td>
        </tr>
        <tr>
          <td style="padding:6px 0"><b>ETH</b></td>
          <td style="text-align:right">{_p(eth.get('price', 0))}</td>
          <td style="text-align:right;opacity:0.8">{'+' if eth.get('change', 0) >= 0 else ''}{eth.get('change', 0):.1f}%</td>
        </tr>
        <tr><td colspan="3" style="padding:8px 0 4px;border-top:1px solid rgba(0,0,0,0.06)">
          <span style="opacity:0.7">Trend</span> <b>{score}</b>/100 · {slabel}
          &nbsp;&nbsp;
          <span style="opacity:0.7">F&G</span> <b>{fng_val}</b> · {fng_tag}
        </td></tr>
      </table>
    </div>"""

    # ═══ 一、AI 今日要点（最重要，放最前面）═══
    ai_summary = data.get("ai_summary", "")
    if ai_summary:
        h += '<div class="s"><p class="st">AI 今日要点</p>'
        h += f'<div class="sb">{ai_summary.replace(chr(10), "<br>")}</div>'
        h += '</div>'

    # ═══ 二、风险仪表盘（合并：衍生品+清算+多空+Gas）═══
    h += '<div class="s"><p class="st">风险仪表盘</p>'

    # 资金费率（只显示 BTC 主要的）
    if funding:
        for sym in ["BTC", "ETH", "SOL"]:
            if sym in funding:
                rate = funding[sym]
                tag = _ftag("过热", "r") if rate > FUNDING_HOT else _ftag("过冷", "b") if rate < FUNDING_COLD else _ftag("中性", "g")
                h += f'<div class="r"><span class="l">{sym} 费率</span><span class="v">{rate:.4f}% {tag}</span></div>'

    # RSI
    for rlabel, rsi in [("BTC RSI", btc_rsi), ("ETH RSI", eth_rsi)]:
        if rsi is not None:
            tag = _ftag("超买", "r") if rsi >= RSI_OVERBOUGHT else _ftag("超卖", "b") if rsi <= RSI_OVERSOLD else ""
            h += f'<div class="r"><span class="l">{rlabel}</span><span class="v">{rsi:.0f} {tag}</span></div>'

    # 多空比（合并显示）
    if ls:
        h += '<div class="dv"></div>'
        for sym in ["BTC", "ETH"]:
            if sym in ls:
                lp = ls[sym]["long_pct"]
                tag = _ftag("多头拥挤", "r") if lp > 65 else _ftag("空头拥挤", "g") if lp < 35 else ""
                h += f'<div class="r"><span class="l">{sym} 多空</span><span class="v">L {lp:.0f}% / S {100-lp:.0f}% {tag}</span></div>'

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

    # ═══ 期权交割日历 ═══
    options = data.get("options_expiry", {})
    if options:
        h += '<div class="s"><p class="st">期权交割日历</p>'
        for currency in ["BTC", "ETH"]:
            if currency not in options or not options[currency]:
                continue
            for exp in options[currency]:
                days = exp["days_left"]
                tag = _ftag("重大交割", "r") if exp["is_major"] else ""
                if days <= 3:
                    tag += _ftag(f"⚠ {days}天后", "r")
                elif days <= 7:
                    tag += _ftag(f"{days}天后", "y")
                h += f'<div class="r"><span class="l">{currency} {exp["date_fmt"]}</span>'
                h += f'<span class="v">{_mc(exp["notional_usd"])} ({exp["oi_coins"]:,.0f}枚) {tag}</span></div>'
        h += '</div>'

    # ═══ 机构持仓 · 大额动向 ═══
    holdings = data.get("institutional", {})
    if holdings:
        h += '<div class="s"><p class="st">机构持仓 · 大额动向</p>'
        for sym in ["BTC", "ETH"]:
            if sym not in holdings:
                continue
            hd = holdings[sym]
            h += f'<div class="r"><span class="l">{sym} 机构总持仓</span><span class="v">{_mc(hd["total_value_usd"])}</span></div>'
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
    h += '<div class="s"><p class="st">资金 & 宏观</p>'

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
    for pair in ["USD/JPY", "USD/CNY"]:
        if pair in forex:
            h += f'<div class="r"><span class="l">{pair}</span><span class="v">{forex[pair]:.2f}</span></div>'
    h += '</div>'

    # ═══ 四、行情 + 涨跌榜（合并）═══
    h += '<div class="s"><p class="st">行情一览</p>'

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
        h += '<div class="s"><p class="st">涨幅筛选 · 跑赢BTC</p>'

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
            h += f'<p style="font-size:11px;color:#b0a898;margin:8px 0 4px;font-weight:600">{label} · 前200 ({len(top200)}个)</p>'
            for coin in top200[:3]:
                h += f'<div class="r"><span class="l">#{coin["rank"]} {coin["symbol"]}</span>'
                h += f'<span class="v">{coin["change"]:+.1f}% <span style="font-size:10px;color:#34a853">+{coin["vs_btc"]:.1f}%</span></span></div>'
            if len(top200) > 3:
                h += f'<p style="font-size:10px;color:#c7c7cc;text-align:center">...及其余 {len(top200)-3} 个</p>'

            if after200:
                h += '<div class="dv"></div>'
                h += f'<p style="font-size:11px;color:#b0a898;margin:8px 0 4px;font-weight:600">{label} · 200名后 ({len(after200)}个)</p>'
                for coin in after200[:3]:
                    h += f'<div class="r"><span class="l">#{coin["rank"]} {coin["symbol"]}</span>'
                    h += f'<span class="v">{coin["change"]:+.1f}% <span style="font-size:10px;color:#34a853">+{coin["vs_btc"]:.1f}%</span></span></div>'
                if len(after200) > 3:
                    h += f'<p style="font-size:10px;color:#c7c7cc;text-align:center">...及其余 {len(after200)-3} 个</p>'

        h += '</div>'

    # ═══ 六、新闻 + 决策参考（合并）═══
    h += '<div class="s"><p class="st">新闻 & 研判</p>'

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
            h += '<div class="ni">'
            if link:
                h += f'<a href="{link}">{title}</a>{urgent_tag}'
            else:
                h += f'{title}{urgent_tag}'
            if source:
                h += f'<span class="sm">{source}</span>'
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
    h += f'<div class="hd" style="border-left:3px solid #ea4335"><p class="sub">TRIGGER ALERT</p><h1>Alert</h1><p class="t">{ts} CST</p></div>'

    for section in alerts:
        h += f'<div class="s"><p class="st">{section["title"]}</p>'
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

def push_wechat(title: str, html_body: str):
    for token in PUSHPLUS_TOKENS:
        token = token.strip()
        if not token:
            continue
        payload = json.dumps({
            "token": token, "title": title,
            "content": html_body, "template": "html",
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
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[OK] 邮件已发送: {EMAIL_TO}")
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
    }

    # 趋势评分
    data["trend_score"] = calculate_trend_score(data)

    liq_total = data["liquidations"].get("total_24h", 0)
    screening = data.get("screening", {})
    ops_count = sum(len(v) for v in screening.get("outperformers", {}).values())
    opt_btc = len(data.get("options_expiry", {}).get("BTC", []))
    print(f"[INFO] 币价:{len(data['prices'])} 费率:{len(data['funding'])} "
          f"宏观:{len(data['yields'])} 清算:{_mc(liq_total)} "
          f"多空:{len(data['long_short'])} Gas:{data['gas_fee'].get('standard', '?')} "
          f"TVL:{_mc(data['defi_tvl'].get('total_tvl', 0))} "
          f"趋势:{data['trend_score']} 新闻:{len(data['news'])} "
          f"期权到期:{opt_btc} 跑赢BTC:{ops_count}个")

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
    screening = _safe_fetch(fetch_top200_vs_btc, {})
    options = _safe_fetch(fetch_options_expiry, {})
    coin_liq = _safe_fetch(fetch_coin_liquidations, {})
    institutional = _safe_fetch(fetch_institutional_holdings, {})

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
    h += '<div class="s"><p class="st">市场概览</p>'
    h += f'<div class="r"><span class="l">BTC</span><span class="v">{_p(btc.get("price", 0))} {_c(btc.get("change", 0))}</span></div>'
    h += f'<div class="r"><span class="l">ETH</span><span class="v">{_p(eth.get("price", 0))} {_c(eth.get("change", 0))}</span></div>'
    fng_val = fng.get("value", 0)
    h += f'<div class="r"><span class="l">恐贪指数</span><span class="v">{fng_val} · {fng.get("label", "")}</span></div>'
    if gd:
        h += f'<div class="r"><span class="l">总市值</span><span class="v">{_mc(gd.get("total_market_cap", 0))}</span></div>'
        h += f'<div class="r"><span class="l">BTC 市占</span><span class="v">{gd.get("btc_dominance", 0):.1f}%</span></div>'
    h += '</div>'

    # 期权交割日历
    if options:
        h += '<div class="s"><p class="st">期权交割日历</p>'
        for currency in ["BTC", "ETH"]:
            if currency not in options or not options[currency]:
                continue
            for exp in options[currency]:
                days = exp["days_left"]
                tag = _ftag("重大交割", "r") if exp["is_major"] else ""
                if days <= 3:
                    tag += _ftag(f"⚠ {days}天后", "r")
                elif days <= 7:
                    tag += _ftag(f"{days}天后", "y")
                h += f'<div class="r"><span class="l">{currency} {exp["date_fmt"]}</span>'
                h += f'<span class="v">{_mc(exp["notional_usd"])} ({exp["oi_coins"]:,.0f}枚) {tag}</span></div>'
        h += '</div>'

    # BTC/ETH 逐币持仓
    if coin_liq:
        h += '<div class="s"><p class="st">BTC/ETH 衍生品持仓</p>'
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
        h += '<div class="s"><p class="st">机构持仓 · 大额动向</p>'
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

    # 涨幅筛选（全量展示，周报核心内容）
    if screening and screening.get("outperformers"):
        h += '<div class="s"><p class="st">涨幅筛选 · 跑赢BTC (全量)</p>'

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
    """紧急新闻检查：RSS 抓取 + 价格异动"""
    print("[INFO] === 紧急新闻检查 ===")
    news = fetch_news()
    urgent_news = [n for n in news if n.get("urgent")]

    prices = fetch_prices()

    sections = []

    # 紧急新闻
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
