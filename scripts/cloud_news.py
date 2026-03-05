"""
cloud_news.py - 云端新闻抓取 + 多渠道推送
支持两种模式：
  daily  - 每日简报（金融详细 + 热门精选）
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
    "https://cointelegraph.com/rss",          # CoinTelegraph
    "https://feeds.feedburner.com/CoinDesk",   # CoinDesk
    "https://www.theblock.co/rss.xml",         # The Block
    "https://cryptopanic.com/news/rss/",       # CryptoPanic（聚合币圈社交热门）
    # 综合财经
    "https://36kr.com/feed",                   # 36氪
]

# ── 金融关键词 ────────────────────────────────────────────────────
FINANCE_KEYWORDS = [
    # 币圈
    "BTC", "Bitcoin", "比特币", "ETH", "以太坊", "加密货币", "Crypto",
    "币圈", "代币", "交易所", "Binance", "Coinbase", "稳定币",
    "DeFi", "NFT", "Web3", "区块链", "矿", "链上",
    # 美股
    "美股", "纳斯达克", "标普", "道琼斯", "华尔街",
    "NASDAQ", "S&P", "特斯拉", "苹果", "英伟达", "Meta", "谷歌",
    "美联储", "Fed", "降息", "加息", "利率", "通胀", "CPI", "非农",
    "财报", "营收", "市值", "IPO", "熔断",
    # 黄金/大宗
    "黄金", "Gold", "白银", "原油", "大宗商品",
    # 通用金融
    "股市", "暴跌", "暴涨", "崩盘", "牛市", "熊市", "做空",
    "融资", "投资", "估值", "上市", "退市",
]

# 紧急事件关键词（触发即时推送）
URGENT_KEYWORDS = [
    "暴跌", "暴涨", "崩盘", "熔断", "跳水", "飙升", "历史新高", "历史新低",
    "紧急", "突发", "黑天鹅", "重磅", "央行", "美联储",
    "降息", "加息", "战争", "制裁", "禁令",
]

CST = timezone(timedelta(hours=8))
DATE_FMT = "%Y-%m-%d"

PUSHPLUS_TOKENS = os.environ.get("PUSHPLUS_TOKENS", "").split(",")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

MAX_TRENDING = 5  # 热门精选最多显示几条


def fetch_rss(url: str) -> str:
    headers = {"User-Agent": "CloudNewsBot/1.0"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(text)).strip()


def summarize(text: str, max_len: int = 60) -> str:
    text = strip_html(text).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def classify(title: str, description: str) -> str:
    combined = f"{title} {description}"
    for kw in FINANCE_KEYWORDS:
        if kw in combined:
            return "finance"
    return "other"


def is_urgent(title: str, description: str) -> bool:
    combined = f"{title} {description}"
    finance = any(kw in combined for kw in FINANCE_KEYWORDS)
    urgent = any(kw in combined for kw in URGENT_KEYWORDS)
    return finance and urgent


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


def build_daily_html(finance_items: list[dict], trending_items: list[dict], today: str) -> str:
    now = datetime.now(CST).strftime('%H:%M')
    html = f"""<h1 style="color:#333;">{today} 每日金融简报</h1>
<p style="color:#888;">自动生成于 {now} CST</p><hr>"""

    if finance_items:
        html += '<h2 style="color:#e67e22;">金融市场</h2>'
        for item in finance_items:
            title = item["title"]
            summary = summarize(item["description"])
            link = item["link"]
            html += f'''<div style="margin-bottom:12px;padding:10px;background:#fef9e7;border-left:4px solid #e67e22;">
<strong>{title}</strong><br>
<span style="color:#666;">{summary}</span><br>'''
            if link:
                html += f'<a href="{link}">阅读原文</a>'
            html += '</div>'

    if trending_items:
        html += '<h2 style="color:#3498db;">热门精选</h2>'
        for item in trending_items[:MAX_TRENDING]:
            title = item["title"]
            link = item["link"]
            if link:
                html += f'<p>- <a href="{link}">{title}</a></p>'
            else:
                html += f'<p>- {title}</p>'

    if not finance_items and not trending_items:
        html += '<p style="color:#999;">今日暂无重要新闻</p>'

    html += f'<hr><p style="color:#aaa;font-size:12px;">GitHub Actions 自动生成 | {today}</p>'
    return html


def build_urgent_html(urgent_items: list[dict]) -> str:
    now = datetime.now(CST).strftime('%H:%M')
    html = f"""<h1 style="color:#c0392b;">紧急金融快讯</h1>
<p style="color:#888;">{now} CST</p><hr>"""

    for item in urgent_items:
        title = item["title"]
        summary = summarize(item["description"])
        link = item["link"]
        html += f'''<div style="margin-bottom:12px;padding:10px;background:#fdedec;border-left:4px solid #c0392b;">
<strong>{title}</strong><br>
<span style="color:#666;">{summary}</span><br>'''
        if link:
            html += f'<a href="{link}">阅读原文</a>'
        html += '</div>'

    html += '<hr><p style="color:#aaa;font-size:12px;">GitHub Actions 紧急推送</p>'
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

    finance_items = []
    other_items = []
    seen_titles = set()

    for item in all_items:
        if item["title"] in seen_titles:
            continue
        seen_titles.add(item["title"])
        cat = classify(item["title"], item["description"])
        if cat == "finance":
            finance_items.append(item)
        else:
            other_items.append(item)

    print(f"[INFO] 金融: {len(finance_items)} 条, 其他: {len(other_items)} 条")

    html = build_daily_html(finance_items, other_items, today)
    push_all(f"{today} 每日金融简报", html)


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
        push_all(f"紧急金融快讯（{len(urgent_items)}条）", html)
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
