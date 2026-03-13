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
    """抓取 RSS 新闻，过滤币圈相关，翻译标题"""
    all_items = []
    for feed_url in RSS_FEEDS:
        print(f"[INFO] 抓取: {feed_url}")
        try:
            xml_text = fetch_text(feed_url)
        except (URLError, OSError) as e:
            print(f"[ERROR] 失败: {e}")
            continue
        items = parse_feed(xml_text)
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
body{font-family:-apple-system,'Helvetica Neue','PingFang SC','Hiragino Sans',sans-serif;background:#f5f5f7;color:#1d1d1f;padding:16px;-webkit-font-smoothing:antialiased}
.c{max-width:560px;margin:0 auto;background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 1px 8px rgba(0,0,0,.06)}
.hd{padding:28px 24px 16px}
.hd h1{font-size:20px;font-weight:600;letter-spacing:-.3px}
.hd .t{font-size:12px;color:#86868b;margin-top:2px}
.s{padding:16px 24px;border-top:1px solid #f0f0f2}
.st{font-size:10px;font-weight:600;color:#86868b;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px}
.r{display:flex;justify-content:space-between;align-items:center;padding:5px 0;font-size:13px;line-height:1.4}
.r .l{color:#424245}.r .v{font-weight:500;font-variant-numeric:tabular-nums;text-align:right}
.up{color:#34c759}.dn{color:#ff3b30}.nt{color:#86868b}
.tg{display:inline-block;font-size:10px;font-weight:500;padding:2px 7px;border-radius:4px;margin-left:4px}
.tg-r{background:#fff0f0;color:#ff3b30}.tg-b{background:#f0f8ff;color:#007aff}
.tg-g{background:#f0faf0;color:#34c759}.tg-y{background:#fffbf0;color:#ff9500}
.dv{height:1px;background:#f0f0f2;margin:3px 0}
.ab{margin:6px 0;padding:10px 14px;border-radius:10px;font-size:12px;line-height:1.5}
.ab-d{background:#fff5f5;border:1px solid #ffe0e0}.ab-i{background:#f0f8ff;border:1px solid #d0e8ff}
.sb{background:#f5f5f7;border-radius:10px;padding:12px 14px;margin-top:8px;font-size:12px;line-height:1.7;color:#424245}
.ni{padding:8px 12px;border-left:2px solid #d2d2d7;margin:6px 0;font-size:12px;line-height:1.5}
.ni a{color:#0066cc;text-decoration:none}.ni .sm{color:#86868b;font-size:11px}
.ft{padding:14px 24px;text-align:center;font-size:10px;color:#c7c7cc;border-top:1px solid #f0f0f2}
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

    prices = data["prices"]
    stables = data["stablecoins"]
    forex = data["forex"]
    fng = data["fng"]
    gd = data["global"]
    funding = data["funding"]
    yields = data["yields"]
    btc_rsi = data["btc_rsi"]
    eth_rsi = data["eth_rsi"]
    news = data["news"]

    h = f'<!DOCTYPE html><html><head><meta charset="utf-8">{STYLE}</head><body><div class="c">'

    # Header
    h += f'<div class="hd"><h1>Market Digest</h1><p class="t">{d} · {t} CST</p></div>'

    # ── 一、资金面 ──
    h += '<div class="s"><p class="st">资金面</p>'
    for sym in ["USDT", "USDC"]:
        if sym in stables:
            sc = stables[sym]
            arrow = "↑" if sc["mcap_change_pct"] > 0 else "↓" if sc["mcap_change_pct"] < 0 else "—"
            h += f'<div class="r"><span class="l">{sym} 市值</span><span class="v">{_mc(sc["mcap"])} {arrow} {_c(sc["mcap_change_pct"])}</span></div>'
    if gd:
        h += f'<div class="r"><span class="l">加密总市值</span><span class="v">{_mc(gd.get("total_market_cap", 0))}</span></div>'
        h += f'<div class="r"><span class="l">BTC 市占率</span><span class="v">{gd.get("btc_dominance", 0):.1f}%</span></div>'
        h += f'<div class="r"><span class="l">24h 交易量</span><span class="v">{_mc(gd.get("total_volume", 0))}</span></div>'
    h += '</div>'

    # ── 二、宏观环境 ──
    h += '<div class="s"><p class="st">宏观环境</p>'
    if "US10Y" in yields:
        y = yields["US10Y"]
        h += f'<div class="r"><span class="l">US 10Y 国债</span><span class="v">{y["value"]:.2f}% {_arrow(y["value"], y.get("prev"))}</span></div>'
    if "JP10Y" in yields:
        y = yields["JP10Y"]
        h += f'<div class="r"><span class="l">JP 10Y 国债</span><span class="v">{y["value"]:.2f}% {_arrow(y["value"], y.get("prev"))}</span></div>'
    for pair in ["USD/JPY", "USD/CNY"]:
        if pair in forex:
            h += f'<div class="r"><span class="l">{pair}</span><span class="v">{forex[pair]:.2f}</span></div>'
    h += '</div>'

    # ── 三、情绪 & 衍生品 ──
    h += '<div class="s"><p class="st">情绪 & 衍生品</p>'
    if fng:
        val = fng["value"]
        if val <= 25:
            tag = _ftag("极度恐惧", "r")
        elif val <= 45:
            tag = _ftag("恐惧", "y")
        elif val <= 55:
            tag = _ftag("中性", "g")
        elif val <= 75:
            tag = _ftag("贪婪", "y")
        else:
            tag = _ftag("极度贪婪", "r")
        h += f'<div class="r"><span class="l">恐慌贪婪指数</span><span class="v">{val} {tag}</span></div>'

    for label, rsi in [("BTC RSI (14d)", btc_rsi), ("ETH RSI (14d)", eth_rsi)]:
        if rsi is not None:
            tag = ""
            if rsi >= RSI_OVERBOUGHT:
                tag = _ftag("超买", "r")
            elif rsi <= RSI_OVERSOLD:
                tag = _ftag("超卖", "b")
            h += f'<div class="r"><span class="l">{label}</span><span class="v">{rsi:.0f} {tag}</span></div>'

    if funding:
        h += '<div class="dv"></div>'
        for sym, rate in funding.items():
            tag = ""
            if rate > FUNDING_HOT:
                tag = _ftag("过热", "r")
            elif rate < FUNDING_COLD:
                tag = _ftag("过冷", "b")
            else:
                tag = _ftag("中性", "g")
            h += f'<div class="r"><span class="l">{sym} 资金费率</span><span class="v">{rate:.4f}% {tag}</span></div>'
    h += '</div>'

    # ── 四、清算数据 ──
    liq = data.get("liquidations", {})
    if liq and liq.get("total_24h", 0) > 0:
        h += '<div class="s"><p class="st">清算数据 (24h)</p>'
        total = liq["total_24h"]
        longs = liq.get("long_24h", 0)
        shorts = liq.get("short_24h", 0)
        long_pct = liq.get("long_ratio", 50)
        # 判断严重程度
        if total >= LIQUIDATION_ALERT:
            tag = _ftag("大规模清算", "r")
        elif total >= 100_000_000:
            tag = _ftag("较高", "y")
        else:
            tag = _ftag("正常", "g")
        h += f'<div class="r"><span class="l">总清算额</span><span class="v">{_mc(total)} {tag}</span></div>'
        h += f'<div class="r"><span class="l">多头清算</span><span class="v">{_mc(longs)}</span></div>'
        h += f'<div class="r"><span class="l">空头清算</span><span class="v">{_mc(shorts)}</span></div>'
        # 多空比可视化
        bar_w = max(5, min(95, long_pct))
        h += f'<div style="margin-top:6px;height:6px;background:#f0f0f2;border-radius:3px;overflow:hidden">'
        h += f'<div style="width:{bar_w}%;height:100%;background:{"#ff3b30" if long_pct > 60 else "#34c759" if long_pct < 40 else "#86868b"};border-radius:3px"></div></div>'
        h += f'<div class="r"><span class="l" style="font-size:11px">多头 {long_pct:.0f}%</span><span class="v" style="font-size:11px">空头 {100-long_pct:.0f}%</span></div>'
        if liq.get("source") == "binance_sample":
            h += '<p style="font-size:10px;color:#c7c7cc;margin-top:2px">* Binance 样本估算</p>'
        h += '</div>'

    # ── 五、行情一览 ──
    h += '<div class="s"><p class="st">行情一览</p>'
    sorted_prices = sorted(prices.items(), key=lambda x: abs(x[1]["change"]), reverse=True)
    for sym, d_ in sorted_prices:
        h += f'<div class="r"><span class="l">{sym}</span><span class="v">{_p(d_["price"])} {_c(d_["change"])}</span></div>'
    h += '</div>'

    # ── 六、涨跌榜 ──
    by_change = sorted(prices.items(), key=lambda x: x[1]["change"], reverse=True)
    gainers = [(s, d_) for s, d_ in by_change[:3] if d_["change"] > 0]
    losers = [(s, d_) for s, d_ in by_change[-3:] if d_["change"] < 0]
    if gainers or losers:
        h += '<div class="s"><p class="st">涨跌榜</p>'
        if gainers:
            tags = " ".join(_ftag(f'{s} +{d_["change"]:.1f}%', "g") for s, d_ in gainers)
            h += f'<p style="margin:2px 0;font-size:12px;">领涨 {tags}</p>'
        if losers:
            tags = " ".join(_ftag(f'{s} {d_["change"]:.1f}%', "r") for s, d_ in losers)
            h += f'<p style="margin:2px 0;font-size:12px;">领跌 {tags}</p>'
        h += '</div>'

    # ── 七、AI 今日要点 ──
    ai_summary = data.get("ai_summary", "")
    if ai_summary:
        h += '<div class="s"><p class="st">AI 今日要点</p>'
        h += f'<div class="sb">{ai_summary.replace(chr(10), "<br>")}</div>'
        h += '</div>'

    # ── 八、新闻速览 ──
    if news:
        h += '<div class="s"><p class="st">新闻速览</p>'
        for item in news[:MAX_NEWS]:
            title = item.get("title_cn", item["title"])
            link = item.get("link", "")
            summary = item.get("summary_cn", "")
            urgent_tag = _ftag("重要", "r") if item.get("urgent") else ""
            h += '<div class="ni">'
            if link:
                h += f'<a href="{link}">{title}</a>{urgent_tag}'
            else:
                h += f'{title}{urgent_tag}'
            if summary:
                h += f'<br><span class="sm">{summary}</span>'
            h += '</div>'
        h += '</div>'

    # ── 九、决策参考 ──
    h += '<div class="s"><p class="st">决策参考</p>'
    summary = _generate_summary(data)
    h += f'<div class="sb">{summary}</div>'
    h += '</div>'

    # Footer
    h += f'<div class="ft">GitHub Actions · {d}</div>'
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
    h += f'<div class="hd"><h1 style="color:#ff3b30;">Alert</h1><p class="t">{ts} CST</p></div>'

    for section in alerts:
        h += f'<div class="s"><p class="st">{section["title"]}</p>'
        for item in section["items"]:
            cls = "ab-d" if section.get("danger") else "ab-i"
            h += f'<div class="ab {cls}">{item}</div>'
        h += '</div>'

    h += f'<div class="ft">GitHub Actions Alert · {ts}</div>'
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
        "news": news,
        "ai_summary": generate_ai_summary(news, prices, fng),
    }

    liq_total = data["liquidations"].get("total_24h", 0)
    print(f"[INFO] 币价:{len(data['prices'])} 费率:{len(data['funding'])} "
          f"宏观:{len(data['yields'])} 清算:{_mc(liq_total)} 新闻:{len(data['news'])}")

    html = build_daily_html(data)
    push_all(f"{today} Market Digest", html)


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

    if sections:
        count = sum(len(s["items"]) for s in sections)
        print(f"[ALERT] 推送 {count} 条预警")
        html = build_alert_html(sections)
        push_all("Alert", html)
    else:
        print("[INFO] 无预警触发")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        run_daily()
    elif mode == "alert":
        run_alert()
    else:
        print(f"[ERROR] 未知模式: {mode} (可用: daily / alert)")
        sys.exit(1)


if __name__ == "__main__":
    main()
