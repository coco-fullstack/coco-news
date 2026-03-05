"""
cloud_news.py - 云端新闻抓取 + 多渠道推送
支持两种模式：
  daily  - 每日简报（80%币圈 + 15%金融 + 5%热门/AI）
  urgent - 紧急检查（仅推送重大金融事件）
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
from html import unescape

# ── RSS 源 ────────────────────────────────────────────────────────
RSS_FEEDS = [
    # 币圈（主要）
    "https://cointelegraph.com/rss",
    "https://feeds.feedburner.com/CoinDesk",
    "https://www.theblock.co/rss.xml",
    # 综合财经
    "https://36kr.com/feed",
]

# ── 分类关键词 ────────────────────────────────────────────────────
CRYPTO_KEYWORDS = [
    "BTC", "Bitcoin", "比特币", "ETH", "Ethereum", "以太坊",
    "Solana", "SOL", "XRP", "BNB", "DOGE", "狗狗币",
    "加密货币", "Crypto", "cryptocurrency", "币圈", "代币", "token",
    "交易所", "Binance", "Coinbase", "OKX", "Bybit",
    "稳定币", "stablecoin", "USDT", "USDC",
    "DeFi", "DEX", "NFT", "Web3", "区块链", "blockchain",
    "矿", "mining", "链上", "on-chain", "钱包", "wallet",
    "空投", "airdrop", "质押", "staking", "Layer 2", "L2",
    "SEC", "监管", "regulation",
]

FINANCE_KEYWORDS = [
    "美股", "纳斯达克", "标普", "道琼斯", "华尔街",
    "NASDAQ", "S&P", "Wall Street",
    "特斯拉", "Tesla", "苹果", "Apple", "英伟达", "NVIDIA",
    "美联储", "Fed", "降息", "加息", "利率", "通胀", "CPI", "非农",
    "财报", "earnings", "营收", "市值", "IPO",
    "黄金", "Gold", "白银", "原油", "oil", "大宗商品",
    "股市", "牛市", "熊市", "做空",
    "融资", "投资", "估值", "上市", "退市",
]

AI_KEYWORDS = [
    "AI", "人工智能", "GPT", "大模型", "LLM", "Claude", "OpenAI",
    "Gemini", "机器学习", "深度学习", "AGI", "芯片", "GPU",
]

URGENT_KEYWORDS = [
    "暴跌", "暴涨", "崩盘", "熔断", "跳水", "飙升",
    "历史新高", "历史新低", "all-time high", "ATH",
    "紧急", "突发", "黑天鹅", "重磅", "breaking",
    "央行", "美联储", "降息", "加息",
    "战争", "制裁", "禁令", "crash", "surge", "plunge",
]

CST = timezone(timedelta(hours=8))
DATE_FMT = "%Y-%m-%d"

PUSHPLUS_TOKENS = os.environ.get("PUSHPLUS_TOKENS", "").split(",")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

# 每日简报条数限制
MAX_CRYPTO = 20
MAX_FINANCE = 5
MAX_OTHER = 3


def fetch_rss(url: str) -> str:
    headers = {"User-Agent": "CloudNewsBot/1.0"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(text)).strip()


def summarize(text: str, max_len: int = 80) -> str:
    text = strip_html(text).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


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


def is_urgent(title: str, description: str) -> bool:
    combined = f"{title} {description}".lower()
    has_finance = any(kw.lower() in combined for kw in CRYPTO_KEYWORDS + FINANCE_KEYWORDS)
    has_urgent = any(kw.lower() in combined for kw in URGENT_KEYWORDS)
    return has_finance and has_urgent


def parse_feed(xml_text: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        print("[WARN] RSS XML 解析失败，跳过")
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


def render_section(items: list[dict], color: str, bg: str) -> str:
    html = ""
    for item in items:
        title = item["title"]
        summary = summarize(item["description"])
        link = item["link"]
        html += f'''<div style="margin-bottom:10px;padding:10px;background:{bg};border-left:4px solid {color};">
<strong>{title}</strong><br>
<span style="color:#666;font-size:13px;">{summary}</span><br>'''
        if link:
            html += f'<a href="{link}" style="color:#3498db;font-size:13px;">阅读原文</a>'
        html += '</div>'
    return html


def build_daily_html(crypto: list[dict], finance: list[dict],
                     other: list[dict], today: str) -> str:
    now = datetime.now(CST).strftime('%H:%M')
    html = f"""<h1 style="color:#333;">{today} 每日简报</h1>
<p style="color:#888;font-size:13px;">自动生成于 {now} CST | 币圈 {len(crypto)} 条 · 金融 {len(finance)} 条 · 其他 {len(other)} 条</p><hr>"""

    if crypto:
        html += '<h2 style="color:#f39c12;">币圈动态</h2>'
        html += render_section(crypto, "#f39c12", "#fef9e7")

    if finance:
        html += '<h2 style="color:#e67e22;">金融市场</h2>'
        html += render_section(finance, "#e67e22", "#fdf2e9")

    if other:
        html += '<h2 style="color:#3498db;">热门精选</h2>'
        for item in other:
            title = item["title"]
            link = item["link"]
            if link:
                html += f'<p style="font-size:14px;">· <a href="{link}" style="color:#3498db;">{title}</a></p>'
            else:
                html += f'<p style="font-size:14px;">· {title}</p>'

    if not crypto and not finance and not other:
        html += '<p style="color:#999;">今日暂无重要新闻</p>'

    html += f'<hr><p style="color:#aaa;font-size:11px;">GitHub Actions 自动生成 | {today}</p>'
    return html


def build_urgent_html(urgent_items: list[dict]) -> str:
    now = datetime.now(CST).strftime('%H:%M')
    html = f"""<h1 style="color:#c0392b;">紧急快讯</h1>
<p style="color:#888;">{now} CST</p><hr>"""
    html += render_section(urgent_items, "#c0392b", "#fdedec")
    html += '<hr><p style="color:#aaa;font-size:11px;">GitHub Actions 紧急推送</p>'
    return html


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


def fetch_all_items() -> list[dict]:
    all_items = []
    for feed_url in RSS_FEEDS:
        print(f"[INFO] 抓取 RSS: {feed_url}")
        try:
            xml_text = fetch_rss(feed_url)
        except (URLError, OSError) as e:
            print(f"[ERROR] 抓取失败 {feed_url}: {e}")
            continue
        items = parse_feed(xml_text)
        print(f"[INFO] 解析到 {len(items)} 条")
        all_items.extend(items)
    return all_items


def run_daily():
    today = datetime.now(CST).strftime(DATE_FMT)
    all_items = fetch_all_items()

    crypto_items = []
    finance_items = []
    other_items = []
    seen_titles = set()

    for item in all_items:
        if item["title"] in seen_titles:
            continue
        seen_titles.add(item["title"])
        cat = classify(item["title"], item["description"])
        if cat == "crypto":
            crypto_items.append(item)
        elif cat == "finance":
            finance_items.append(item)
        else:
            other_items.append(item)

    # 按比重限制条数
    crypto_items = crypto_items[:MAX_CRYPTO]
    finance_items = finance_items[:MAX_FINANCE]
    other_items = other_items[:MAX_OTHER]

    print(f"[INFO] 币圈: {len(crypto_items)}, 金融: {len(finance_items)}, 其他: {len(other_items)}")

    html = build_daily_html(crypto_items, finance_items, other_items, today)
    push_all(f"{today} 每日简报", html)


def run_urgent():
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
        print(f"[ALERT] 发现 {len(urgent_items)} 条紧急新闻，立即推送！")
        html = build_urgent_html(urgent_items)
        push_all(f"紧急快讯（{len(urgent_items)}条）", html)
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
