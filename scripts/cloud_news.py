"""
cloud_news.py - 币圈新闻快讯 + 行情推送
风格参考 Binance/OKX 推送：币价行情 + 一句话快讯
支持两种模式：
  daily  - 每日简报
  urgent - 紧急快讯（每2小时检查）
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
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"
TRACKED_COINS = {
    # 主流币
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    # 山寨币/热门
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "avalanche-2": "AVAX",
    "polkadot": "DOT",
    "chainlink": "LINK",
    "sui": "SUI",
    "pepe": "PEPE",
    "shiba-inu": "SHIB",
}

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
    "空投", "airdrop", "质押", "staking", "Layer 2", "L2",
    "SEC", "监管", "regulation", "whale", "鲸鱼",
    "ETF", "现货ETF", "山寨币", "altcoin", "meme币", "memecoin",
    # 大佬名字（新闻源经常提到）
    "CZ", "赵长鹏", "Changpeng Zhao",
    "Elon Musk", "马斯克", "Musk",
    "Vitalik", "V神",
    "Michael Saylor", "MicroStrategy",
    "BlackRock", "贝莱德",
    "Grayscale", "灰度",
]

FINANCE_KEYWORDS = [
    "美股", "纳斯达克", "标普", "道琼斯", "华尔街",
    "NASDAQ", "S&P", "Wall Street",
    "美联储", "Fed", "降息", "加息", "利率", "通胀", "CPI", "非农",
    "黄金", "Gold", "原油", "oil",
    "财报", "earnings", "IPO",
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

# 大佬关键词（匹配到直接归入币圈且优先显示）
VIP_KEYWORDS = [
    "CZ", "赵长鹏", "Changpeng Zhao",
    "Elon Musk", "马斯克", "Musk",
    "Vitalik", "V神",
    "Michael Saylor", "MicroStrategy",
    "Trump", "特朗普",
]

CST = timezone(timedelta(hours=8))
DATE_FMT = "%Y-%m-%d"

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
    """提取一句话摘要"""
    text = strip_html(text).replace("\n", " ").strip()
    # 取第一句话
    for sep in ["。", ".", "！", "!"]:
        idx = text.find(sep)
        if 0 < idx < 200:
            text = text[:idx + 1]
            break
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


# ── 币价获取 ──────────────────────────────────────────────────────

def fetch_prices() -> dict:
    ids = ",".join(TRACKED_COINS.keys())
    url = f"{COINGECKO_API}?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    try:
        data = json.loads(fetch_url(url))
        result = {}
        for coin_id, symbol in TRACKED_COINS.items():
            if coin_id in data:
                price = data[coin_id]["usd"]
                change = data[coin_id].get("usd_24h_change", 0)
                result[symbol] = {"price": price, "change": change}
        return result
    except Exception as e:
        print(f"[ERROR] 币价获取失败: {e}")
        return {}


def format_price(price: float) -> str:
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:.2f}"
    else:
        return f"${price:.4f}"


def price_emoji(change: float) -> str:
    if change >= 5:
        return "🚀"
    elif change >= 0:
        return "📈"
    elif change >= -5:
        return "📉"
    else:
        return "💥"


# ── 分类 ──────────────────────────────────────────────────────────

def classify(title: str, description: str) -> str:
    combined = f"{title} {description}"
    for kw in CRYPTO_KEYWORDS:
        if kw.lower() in combined.lower():
            return "crypto"
    for kw in FINANCE_KEYWORDS:
        if kw.lower() in combined.lower():
            return "finance"
    for kw in AI_KEYWORDS:
        if kw.lower() in combined.lower():
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
        if title:
            items.append({"title": title, "link": link, "description": desc})

    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", "", ns) or "").strip()
            if title:
                items.append({"title": title, "link": link, "description": desc})

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


# ── 翻译处理 ──────────────────────────────────────────────────────

def process_items(items: list[dict]) -> list[dict]:
    """翻译标题为中文，生成一句话摘要"""
    for item in items:
        item["title_cn"] = translate_to_chinese(item["title"])
        desc = strip_html(item["description"])
        if desc:
            summary = one_line_summary(desc)
            item["summary_cn"] = translate_to_chinese(summary)
        else:
            item["summary_cn"] = ""
        item["is_vip"] = is_vip(item["title"], item["description"])
    return items


# ── HTML 构建 ─────────────────────────────────────────────────────

def build_price_html(prices: dict) -> str:
    if not prices:
        return ""
    html = '<div style="background:#1a1a2e;color:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">'
    html += '<p style="color:#aaa;margin:0 0 10px 0;font-size:12px;">实时行情</p>'
    html += '<table style="width:100%;color:#fff;font-size:14px;">'
    for symbol, data in prices.items():
        price_str = format_price(data["price"])
        change = data["change"]
        emoji = price_emoji(change)
        color = "#00d4aa" if change >= 0 else "#ff4757"
        sign = "+" if change >= 0 else ""
        html += f'<tr><td style="padding:3px 0;"><strong>{symbol}</strong></td>'
        html += f'<td style="text-align:right;">{price_str}</td>'
        html += f'<td style="text-align:right;color:{color};">{emoji} {sign}{change:.1f}%</td></tr>'
    html += '</table></div>'
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

        html += f'<div style="margin-bottom:8px;padding:8px 10px;background:#f8f9fa;border-left:3px solid {color};font-size:14px;">'
        html += f'<strong>{title_cn}</strong>{vip_tag}<br>'
        if summary_cn:
            html += f'<span style="color:#888;font-size:12px;">{summary_cn}</span><br>'
        if link:
            html += f'<a href="{link}" style="color:#3498db;font-size:11px;">原文</a>'
        html += '</div>'
    return html


def build_daily_html(prices: dict, crypto: list[dict], finance: list[dict],
                     other: list[dict], today: str) -> str:
    now = datetime.now(CST).strftime('%H:%M')
    html = f'<h2 style="color:#333;margin-bottom:5px;">{today} 每日快讯</h2>'
    html += f'<p style="color:#aaa;font-size:12px;margin-top:0;">{now} CST</p>'

    html += build_price_html(prices)
    html += build_news_html(crypto, f"币圈动态（{len(crypto)}条）", "#f39c12")
    html += build_news_html(finance, f"金融市场（{len(finance)}条）", "#e67e22")
    html += build_news_html(other, f"热门精选（{len(other)}条）", "#3498db")

    if not crypto and not finance and not other:
        html += '<p style="color:#999;">今日暂无重要新闻</p>'

    html += f'<hr style="border:none;border-top:1px solid #eee;"><p style="color:#ccc;font-size:10px;">GitHub Actions 自动推送</p>'
    return html


def build_urgent_html(prices: dict, urgent_items: list[dict]) -> str:
    now = datetime.now(CST).strftime('%H:%M')
    html = f'<h2 style="color:#c0392b;">⚡ 紧急快讯</h2>'
    html += f'<p style="color:#aaa;font-size:12px;">{now} CST</p>'
    html += build_price_html(prices)
    html += build_news_html(urgent_items, "突发事件", "#c0392b")
    html += f'<hr style="border:none;border-top:1px solid #eee;"><p style="color:#ccc;font-size:10px;">GitHub Actions 紧急推送</p>'
    return html


# ── 推送 ──────────────────────────────────────────────────────────

def push_wechat(title: str, html_body: str):
    for token in PUSHPLUS_TOKENS:
        token = token.strip()
        if not token:
            continue
        data = json.dumps({
            "token": token,
            "title": title,
            "content": html_body,
            "template": "html",
        }).encode("utf-8")
        req = Request(
            "http://www.pushplus.plus/send",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
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

    print("[INFO] 获取币价...")
    prices = fetch_prices()

    all_items = fetch_all_items()

    crypto_items = []
    finance_items = []
    other_items = []
    vip_items = []
    seen_titles = set()

    for item in all_items:
        if item["title"] in seen_titles:
            continue
        seen_titles.add(item["title"])

        # 大佬动态优先
        if is_vip(item["title"], item["description"]):
            vip_items.append(item)
            continue

        cat = classify(item["title"], item["description"])
        if cat == "crypto":
            crypto_items.append(item)
        elif cat == "finance":
            finance_items.append(item)
        elif cat == "ai":
            other_items.append(item)
        else:
            other_items.append(item)

    # 大佬动态放在币圈最前面
    crypto_items = vip_items + crypto_items
    crypto_items = crypto_items[:MAX_CRYPTO]
    finance_items = finance_items[:MAX_FINANCE]
    other_items = other_items[:MAX_OTHER]

    print(f"[INFO] 翻译中...")
    crypto_items = process_items(crypto_items)
    finance_items = process_items(finance_items)
    other_items = process_items(other_items)

    print(f"[INFO] 币圈: {len(crypto_items)}, 金融: {len(finance_items)}, 其他: {len(other_items)}")

    html = build_daily_html(prices, crypto_items, finance_items, other_items, today)
    push_all(f"{today} 每日快讯", html)


def run_urgent():
    print("[INFO] 获取币价...")
    prices = fetch_prices()

    all_items = fetch_all_items()

    urgent_items = []
    seen_titles = set()

    for item in all_items:
        if item["title"] in seen_titles:
            continue
        seen_titles.add(item["title"])
        if is_urgent(item["title"], item["description"]):
            urgent_items.append(item)

    if urgent_items:
        urgent_items = process_items(urgent_items)
        print(f"[ALERT] 发现 {len(urgent_items)} 条紧急新闻！")
        html = build_urgent_html(prices, urgent_items)
        push_all(f"⚡ 紧急快讯（{len(urgent_items)}条）", html)
    else:
        print("[INFO] 无紧急新闻，不推送")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        run_daily()
    elif mode == "urgent":
        run_urgent()
    else:
        print(f"[ERROR] 未知模式: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
