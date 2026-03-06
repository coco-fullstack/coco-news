"""
cloud_news.py - 币圈新闻快讯 + 行情推送
模式：
  daily   - 每日简报（行情+恐贪指数+涨跌榜+新闻）
  urgent  - 紧急快讯（新闻异动+价格异动 ±10%）
  weekly  - 每周总结
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

# ── RSS 源 ────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://feeds.feedburner.com/CoinDesk",
    "https://www.theblock.co/rss.xml",
    "https://36kr.com/feed",
]

# ── 币价追踪 ──────────────────────────────────────────────────────
COINGECKO_API = "https://api.coingecko.com/api/v3"
TRACKED_COINS = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
    "binancecoin": "BNB", "ripple": "XRP",
    "dogecoin": "DOGE", "cardano": "ADA", "avalanche-2": "AVAX",
    "polkadot": "DOT", "chainlink": "LINK", "sui": "SUI",
    "pepe": "PEPE", "shiba-inu": "SHIB",
    "uniswap": "UNI", "bittensor": "TAO",
    "kite-2": "KITE", "bio-protocol": "BIO",
}

# 价格提醒阈值
PRICE_ALERTS = {
    "BTC": {"above": 80000, "below": 60000},
    "ETH": {"above": 3000, "below": 1500},
    "SOL": {"above": 150, "below": 50},
}

# 异动阈值：24h涨跌超过此百分比触发推送
PUMP_THRESHOLD = 10

# ── 分类关键词 ────────────────────────────────────────────────────
CRYPTO_KEYWORDS = [
    "BTC", "Bitcoin", "比特币", "ETH", "Ethereum", "以太坊",
    "Solana", "SOL", "XRP", "BNB", "DOGE", "狗狗币",
    "加密货币", "Crypto", "cryptocurrency", "币圈", "代币", "token",
    "交易所", "Binance", "Coinbase", "OKX", "Bybit",
    "稳定币", "stablecoin", "USDT", "USDC",
    "DeFi", "DEX", "NFT", "Web3", "区块链", "blockchain",
    "矿", "mining", "链上", "on-chain", "钱包", "wallet",
    "ADA", "Cardano", "AVAX", "Avalanche", "DOT", "Polkadot",
    "LINK", "Chainlink", "SUI", "PEPE", "SHIB", "柴犬币",
    "MATIC", "Polygon", "ARB", "Arbitrum", "OP", "Optimism",
    "UNI", "Uniswap", "TAO", "Bittensor", "KITE", "BIO", "Bio Protocol",
    "空投", "airdrop", "质押", "staking", "Layer 2", "L2",
    "SEC", "监管", "regulation", "whale", "鲸鱼",
    "ETF", "现货ETF", "山寨币", "altcoin", "meme币", "memecoin",
    "CZ", "赵长鹏", "Changpeng Zhao",
    "Elon Musk", "马斯克", "Musk",
    "Vitalik", "V神", "Michael Saylor", "MicroStrategy",
    "BlackRock", "贝莱德", "Grayscale", "灰度",
]

FINANCE_KEYWORDS = [
    "美股", "纳斯达克", "标普", "道琼斯", "华尔街",
    "NASDAQ", "S&P", "Wall Street",
    "美联储", "Fed", "降息", "加息", "利率", "通胀", "CPI", "非农",
    "黄金", "Gold", "原油", "oil", "财报", "earnings", "IPO",
]

AI_KEYWORDS = [
    "AI", "人工智能", "GPT", "大模型", "LLM", "Claude", "OpenAI",
    "Gemini", "AGI", "芯片", "GPU", "NVIDIA", "英伟达",
]

URGENT_KEYWORDS = [
    "暴跌", "暴涨", "崩盘", "熔断", "跳水", "飙升",
    "历史新高", "历史新低", "all-time high", "ATH",
    "紧急", "突发", "黑天鹅", "重磅", "breaking",
    "央行", "美联储", "降息", "加息",
    "战争", "制裁", "禁令", "crash", "surge", "plunge",
    "hack", "被盗", "exploit", "漏洞",
]

VIP_KEYWORDS = [
    "CZ", "赵长鹏", "Changpeng Zhao",
    "Elon Musk", "马斯克", "Musk",
    "Vitalik", "V神", "Michael Saylor", "MicroStrategy",
    "Trump", "特朗普",
]

CST = timezone(timedelta(hours=8))
DATE_FMT = "%Y-%m-%d"

# RSS 日期格式
RSS_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",      # RFC 822: Mon, 05 Mar 2026 08:00:00 +0000
    "%a, %d %b %Y %H:%M:%S %Z",      # with timezone name
    "%Y-%m-%dT%H:%M:%S%z",            # ISO 8601
    "%Y-%m-%dT%H:%M:%SZ",             # ISO 8601 UTC
]


def parse_pub_date(date_str: str) -> str:
    """解析 RSS 日期，返回北京时间 HH:MM 格式。"""
    if not date_str:
        return ""
    date_str = date_str.strip()
    for fmt in RSS_DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cst = dt.astimezone(CST)
            return dt_cst.strftime("%H:%M")
        except ValueError:
            continue
    return ""

PUSHPLUS_TOKENS = os.environ.get("PUSHPLUS_TOKENS", "").split(",")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

MAX_CRYPTO = 15
MAX_FINANCE = 3
MAX_OTHER = 2


# ── 工具函数 ──────────────────────────────────────────────────────

def fetch_url(url: str) -> str:
    req = Request(url, headers={"User-Agent": "CloudNewsBot/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(text)).strip()


def is_chinese(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def translate_to_chinese(text: str) -> str:
    if is_chinese(text) or not text:
        return text
    try:
        encoded = quote(text[:500])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q={encoded}"
        req = Request(url, headers={"User-Agent": "CloudNewsBot/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return "".join(part[0] for part in data[0] if part[0])
    except Exception:
        return text


def one_line_summary(text: str, max_len: int = 60) -> str:
    text = strip_html(text).replace("\n", " ").strip()
    for sep in ["。", ".", "！", "!"]:
        idx = text.find(sep)
        if 0 < idx < 200:
            text = text[:idx + 1]
            break
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


# ── 市场数据 ──────────────────────────────────────────────────────

def fetch_prices() -> dict:
    ids = ",".join(TRACKED_COINS.keys())
    url = f"{COINGECKO_API}/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    try:
        data = json.loads(fetch_url(url))
        result = {}
        for coin_id, symbol in TRACKED_COINS.items():
            if coin_id in data:
                price = data[coin_id]["usd"]
                change = data[coin_id].get("usd_24h_change", 0) or 0
                result[symbol] = {"price": price, "change": change}
        return result
    except Exception as e:
        print(f"[ERROR] 币价获取失败: {e}")
        return {}


def fetch_fear_greed() -> dict:
    try:
        data = json.loads(fetch_url("https://api.alternative.me/fng/?limit=1"))
        entry = data["data"][0]
        return {"value": int(entry["value"]), "label": entry["value_classification"]}
    except Exception as e:
        print(f"[ERROR] 恐贪指数获取失败: {e}")
        return {}


def fetch_global_data() -> dict:
    try:
        data = json.loads(fetch_url(f"{COINGECKO_API}/global"))
        gd = data["data"]
        return {
            "btc_dominance": gd["market_cap_percentage"].get("btc", 0),
            "eth_dominance": gd["market_cap_percentage"].get("eth", 0),
            "total_market_cap": gd["total_market_cap"].get("usd", 0),
            "total_volume": gd["total_volume"].get("usd", 0),
        }
    except Exception as e:
        print(f"[ERROR] 全局数据获取失败: {e}")
        return {}


def fetch_top_movers() -> dict:
    """获取涨跌幅排行（从已追踪的币中）"""
    prices = fetch_prices()
    if not prices:
        return {"gainers": [], "losers": []}

    sorted_coins = sorted(prices.items(), key=lambda x: x[1]["change"], reverse=True)
    gainers = [(s, d) for s, d in sorted_coins[:5] if d["change"] > 0]
    losers = [(s, d) for s, d in sorted_coins[-5:] if d["change"] < 0]
    losers.reverse()

    return {"gainers": gainers, "losers": losers, "all": prices}


def check_price_alerts(prices: dict) -> list[str]:
    alerts = []
    for symbol, thresholds in PRICE_ALERTS.items():
        if symbol not in prices:
            continue
        price = prices[symbol]["price"]
        if price >= thresholds["above"]:
            alerts.append(f"🚨 {symbol} 突破 ${thresholds['above']:,}！当前 ${price:,.0f}")
        elif price <= thresholds["below"]:
            alerts.append(f"🚨 {symbol} 跌破 ${thresholds['below']:,}！当前 ${price:,.0f}")
    return alerts


def check_pump_dump(prices: dict) -> list[dict]:
    """检测异动币种（±10%以上）"""
    movers = []
    for symbol, data in prices.items():
        if abs(data["change"]) >= PUMP_THRESHOLD:
            direction = "暴涨" if data["change"] > 0 else "暴跌"
            movers.append({
                "symbol": symbol,
                "price": data["price"],
                "change": data["change"],
                "direction": direction,
            })
    return movers


def format_price(price: float) -> str:
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:.2f}"
    elif price >= 0.001:
        return f"${price:.4f}"
    else:
        return f"${price:.8f}"


def price_emoji(change: float) -> str:
    if change >= 10:
        return "🚀"
    elif change >= 5:
        return "🔥"
    elif change >= 0:
        return "📈"
    elif change >= -5:
        return "📉"
    elif change >= -10:
        return "⚠️"
    else:
        return "💥"


# ── 分类 ──────────────────────────────────────────────────────────

def classify(title: str, description: str) -> str:
    combined = f"{title} {description}".lower()
    for kw in CRYPTO_KEYWORDS:
        if kw.lower() in combined:
            return "crypto"
    for kw in FINANCE_KEYWORDS:
        if kw.lower() in combined:
            return "finance"
    for kw in AI_KEYWORDS:
        if kw.lower() in combined:
            return "ai"
    return "other"


def is_vip(title: str, description: str) -> bool:
    combined = f"{title} {description}".lower()
    return any(kw.lower() in combined for kw in VIP_KEYWORDS)


def is_urgent(title: str, description: str) -> bool:
    combined = f"{title} {description}".lower()
    has_finance = any(kw.lower() in combined for kw in CRYPTO_KEYWORDS + FINANCE_KEYWORDS)
    has_urgent = any(kw.lower() in combined for kw in URGENT_KEYWORDS)
    return has_finance and has_urgent


# ── RSS 解析 ──────────────────────────────────────────────────────

def parse_feed(xml_text: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "description": desc, "time": parse_pub_date(pub_date)})
    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", "", ns) or "").strip()
            pub_date = (entry.findtext("atom:published", "", ns)
                        or entry.findtext("atom:updated", "", ns) or "").strip()
            if title:
                items.append({"title": title, "link": link, "description": desc, "time": parse_pub_date(pub_date)})
    return items


def fetch_all_items() -> list[dict]:
    all_items = []
    for feed_url in RSS_FEEDS:
        print(f"[INFO] 抓取: {feed_url}")
        try:
            xml_text = fetch_url(feed_url)
        except (URLError, OSError) as e:
            print(f"[ERROR] 失败: {e}")
            continue
        items = parse_feed(xml_text)
        print(f"[INFO] {len(items)} 条")
        all_items.extend(items)
    return all_items


def process_items(items: list[dict]) -> list[dict]:
    for item in items:
        item["title_cn"] = translate_to_chinese(item["title"])
        desc = strip_html(item["description"])
        if desc:
            item["summary_cn"] = translate_to_chinese(one_line_summary(desc))
        else:
            item["summary_cn"] = ""
        item["is_vip"] = is_vip(item["title"], item["description"])
    return items


# ── HTML 构建 ─────────────────────────────────────────────────────

def build_market_header(prices: dict, fng: dict, global_data: dict) -> str:
    html = '<div style="background:#1a1a2e;color:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">'

    # 恐贪指数 + BTC市占率
    if fng or global_data:
        html += '<div style="display:flex;margin-bottom:10px;">'
        if fng:
            val = fng["value"]
            if val <= 25:
                fng_color = "#ff4757"
                fng_label = "极度恐惧"
            elif val <= 45:
                fng_color = "#ffa502"
                fng_label = "恐惧"
            elif val <= 55:
                fng_color = "#eccc68"
                fng_label = "中性"
            elif val <= 75:
                fng_color = "#7bed9f"
                fng_label = "贪婪"
            else:
                fng_color = "#2ed573"
                fng_label = "极度贪婪"
            html += f'<span style="margin-right:20px;">恐贪指数: <strong style="color:{fng_color};">{val} {fng_label}</strong></span>'
        if global_data:
            btc_dom = global_data.get("btc_dominance", 0)
            html += f'<span>BTC市占: <strong>{btc_dom:.1f}%</strong></span>'
        html += '</div>'

    # 币价表
    html += '<table style="width:100%;color:#fff;font-size:13px;">'
    for symbol, data in prices.items():
        price_str = format_price(data["price"])
        change = data["change"]
        emoji = price_emoji(change)
        color = "#00d4aa" if change >= 0 else "#ff4757"
        sign = "+" if change >= 0 else ""
        html += f'<tr><td style="padding:2px 0;"><strong>{symbol}</strong></td>'
        html += f'<td style="text-align:right;">{price_str}</td>'
        html += f'<td style="text-align:right;color:{color};width:90px;">{emoji} {sign}{change:.1f}%</td></tr>'
    html += '</table></div>'
    return html


def build_movers_html(movers: dict) -> str:
    gainers = movers.get("gainers", [])
    losers = movers.get("losers", [])
    if not gainers and not losers:
        return ""

    html = '<div style="margin-bottom:15px;">'
    if gainers:
        html += '<h3 style="color:#2ed573;margin:10px 0 5px 0;">📈 涨幅榜</h3>'
        for symbol, data in gainers:
            html += f'<span style="display:inline-block;background:#2ed57320;color:#2ed573;padding:3px 8px;margin:2px;border-radius:4px;font-size:13px;">{symbol} +{data["change"]:.1f}%</span>'
    if losers:
        html += '<h3 style="color:#ff4757;margin:10px 0 5px 0;">📉 跌幅榜</h3>'
        for symbol, data in losers:
            html += f'<span style="display:inline-block;background:#ff475720;color:#ff4757;padding:3px 8px;margin:2px;border-radius:4px;font-size:13px;">{symbol} {data["change"]:.1f}%</span>'
    html += '</div>'
    return html


def build_alerts_html(alerts: list[str]) -> str:
    if not alerts:
        return ""
    html = '<div style="background:#fdedec;border:1px solid #c0392b;padding:10px;border-radius:6px;margin-bottom:15px;">'
    for alert in alerts:
        html += f'<p style="margin:3px 0;font-size:14px;"><strong>{alert}</strong></p>'
    html += '</div>'
    return html


def build_pump_dump_html(movers: list[dict], related_news: list[dict]) -> str:
    if not movers:
        return ""
    html = '<div style="background:#1a1a2e;color:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">'
    html += '<h3 style="color:#ff6348;margin:0 0 10px 0;">⚡ 异动币种（24h ±10%+）</h3>'
    for m in movers:
        color = "#2ed573" if m["change"] > 0 else "#ff4757"
        sign = "+" if m["change"] > 0 else ""
        html += f'<p style="margin:5px 0;font-size:14px;"><strong>{m["symbol"]}</strong> {m["direction"]} '
        html += f'<span style="color:{color};">{sign}{m["change"]:.1f}%</span> '
        html += f'当前 {format_price(m["price"])}</p>'

    if related_news:
        html += '<p style="color:#aaa;font-size:12px;margin:8px 0 3px 0;">可能相关新闻：</p>'
        for item in related_news[:3]:
            title_cn = item.get("title_cn", item["title"])
            link = item["link"]
            html += f'<p style="margin:2px 0;font-size:12px;">· '
            if link:
                html += f'<a href="{link}" style="color:#74b9ff;">{title_cn}</a>'
            else:
                html += title_cn
            html += '</p>'

    html += '</div>'
    return html


def build_news_html(items: list[dict], section_title: str, color: str) -> str:
    if not items:
        return ""
    html = f'<h3 style="color:{color};margin:15px 0 8px 0;">{section_title}</h3>'
    for item in items:
        title_cn = item.get("title_cn", item["title"])
        summary_cn = item.get("summary_cn", "")
        link = item["link"]
        vip_tag = ' <span style="background:#ff6b6b;color:#fff;font-size:10px;padding:1px 4px;border-radius:3px;">大佬</span>' if item.get("is_vip") else ""
        time_str = item.get("time", "")
        time_tag = f' <span style="color:#aaa;font-size:11px;">{time_str}</span>' if time_str else ""
        html += f'<div style="margin-bottom:8px;padding:8px 10px;background:#f8f9fa;border-left:3px solid {color};font-size:14px;">'
        html += f'<strong>{title_cn}</strong>{vip_tag}{time_tag}<br>'
        if summary_cn:
            html += f'<span style="color:#888;font-size:12px;">{summary_cn}</span><br>'
        if link:
            html += f'<a href="{link}" style="color:#3498db;font-size:11px;">原文</a>'
        html += '</div>'
    return html


# ── 推送 ──────────────────────────────────────────────────────────

def push_wechat(title: str, html_body: str):
    for token in PUSHPLUS_TOKENS:
        token = token.strip()
        if not token:
            continue
        data = json.dumps({
            "token": token, "title": title,
            "content": html_body, "template": "html",
        }).encode("utf-8")
        req = Request("http://www.pushplus.plus/send", data=data,
                      headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                if result.get("code") == 200:
                    print(f"[OK] 微信推送成功: token={token[:8]}...")
                else:
                    print(f"[WARN] 微信推送异常: {result}")
        except (URLError, OSError) as e:
            print(f"[ERROR] 微信推送失败: {e}")


def send_email(subject: str, html_body: str):
    if not SMTP_USER or not SMTP_PASS or not EMAIL_TO:
        print("[SKIP] 邮件未配置，跳过")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
    print(f"[OK] 邮件已发送至 {EMAIL_TO}")


def push_all(title: str, html_body: str):
    push_wechat(title, html_body)
    send_email(title, html_body)


# ── 主逻辑 ────────────────────────────────────────────────────────

def run_daily():
    today = datetime.now(CST).strftime(DATE_FMT)
    now = datetime.now(CST).strftime('%H:%M')

    print("[INFO] 获取市场数据...")
    movers_data = fetch_top_movers()
    prices = movers_data.get("all", {})
    fng = fetch_fear_greed()
    global_data = fetch_global_data()

    all_items = fetch_all_items()
    crypto_items, finance_items, other_items, vip_items = [], [], [], []
    seen = set()

    for item in all_items:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        if is_vip(item["title"], item["description"]):
            vip_items.append(item)
        elif classify(item["title"], item["description"]) == "crypto":
            crypto_items.append(item)
        elif classify(item["title"], item["description"]) == "finance":
            finance_items.append(item)
        else:
            other_items.append(item)

    crypto_items = (vip_items + crypto_items)[:MAX_CRYPTO]
    finance_items = finance_items[:MAX_FINANCE]
    other_items = other_items[:MAX_OTHER]

    print("[INFO] 翻译中...")
    crypto_items = process_items(crypto_items)
    finance_items = process_items(finance_items)
    other_items = process_items(other_items)

    # 价格提醒
    alerts = check_price_alerts(prices)

    print(f"[INFO] 币圈: {len(crypto_items)}, 金融: {len(finance_items)}, 其他: {len(other_items)}")

    # 构建 HTML
    html = f'<h2 style="color:#333;margin-bottom:5px;">{today} 每日快讯</h2>'
    html += f'<p style="color:#aaa;font-size:12px;margin-top:0;">{now} CST</p>'
    html += build_alerts_html(alerts)
    html += build_market_header(prices, fng, global_data)
    html += build_movers_html(movers_data)
    html += build_news_html(crypto_items, f"币圈动态（{len(crypto_items)}条）", "#f39c12")
    html += build_news_html(finance_items, f"金融市场（{len(finance_items)}条）", "#e67e22")
    html += build_news_html(other_items, f"热门精选（{len(other_items)}条）", "#3498db")
    html += '<hr style="border:none;border-top:1px solid #eee;"><p style="color:#ccc;font-size:10px;">GitHub Actions 自动推送</p>'

    push_all(f"{today} 每日快讯", html)


def run_urgent():
    now_str = datetime.now(CST).strftime('%H:%M')
    print("[INFO] 获取币价...")
    prices = fetch_prices()

    should_push = False
    html = f'<h2 style="color:#c0392b;">⚡ 紧急快讯</h2>'
    html += f'<p style="color:#aaa;font-size:12px;">{now_str} CST</p>'

    # 1. 价格提醒
    alerts = check_price_alerts(prices)
    if alerts:
        should_push = True
        html += build_alerts_html(alerts)

    # 2. 异动检测（±10%）
    pump_dump = check_pump_dump(prices)

    # 3. 紧急新闻
    all_items = fetch_all_items()
    urgent_items = []
    seen = set()
    for item in all_items:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        if is_urgent(item["title"], item["description"]):
            urgent_items.append(item)

    if pump_dump:
        should_push = True
        # 找异动币相关新闻
        mover_symbols = [m["symbol"].lower() for m in pump_dump]
        related = [it for it in all_items
                   if any(s in it["title"].lower() for s in mover_symbols)]
        related = process_items(related[:3]) if related else []
        html += build_pump_dump_html(pump_dump, related)

    if urgent_items:
        should_push = True
        urgent_items = process_items(urgent_items[:5])
        html += build_news_html(urgent_items, "突发事件", "#c0392b")

    if should_push:
        html += build_market_header(prices, {}, {})
        html += '<hr style="border:none;border-top:1px solid #eee;"><p style="color:#ccc;font-size:10px;">GitHub Actions 紧急推送</p>'
        count = len(alerts) + len(pump_dump) + len(urgent_items)
        print(f"[ALERT] 推送 {count} 条紧急信息")
        push_all(f"⚡ 紧急快讯", html)
    else:
        print("[INFO] 无紧急情况，不推送")


def run_weekly():
    today = datetime.now(CST)
    week_start = (today - timedelta(days=7)).strftime(DATE_FMT)
    today_str = today.strftime(DATE_FMT)
    now = today.strftime('%H:%M')

    print("[INFO] 获取市场数据...")
    prices = fetch_prices()
    fng = fetch_fear_greed()
    global_data = fetch_global_data()
    movers_data = fetch_top_movers()

    all_items = fetch_all_items()
    crypto_items, vip_items = [], []
    seen = set()

    for item in all_items:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        if is_vip(item["title"], item["description"]):
            vip_items.append(item)
        elif classify(item["title"], item["description"]) == "crypto":
            crypto_items.append(item)

    top_news = process_items((vip_items + crypto_items)[:10])

    html = f'<h2 style="color:#333;">📊 周报 {week_start} ~ {today_str}</h2>'
    html += f'<p style="color:#aaa;font-size:12px;">{now} CST</p>'
    html += build_market_header(prices, fng, global_data)
    html += build_movers_html(movers_data)
    html += build_news_html(top_news, "本周重要新闻", "#9b59b6")
    html += '<hr style="border:none;border-top:1px solid #eee;"><p style="color:#ccc;font-size:10px;">GitHub Actions 周报推送</p>'

    push_all(f"📊 周报 {week_start}~{today_str}", html)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        run_daily()
    elif mode == "urgent":
        run_urgent()
    elif mode == "weekly":
        run_weekly()
    else:
        print(f"[ERROR] 未知模式: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
