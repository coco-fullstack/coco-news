"""
cloud_news.py - 云端新闻抓取 + 多渠道推送
每日定时抓取 RSS 源，按"工作/生活"分流，通过 PushPlus（微信）和邮件推送。
"""

import json
import os
import re
import smtplib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import unescape

# ── 配置 ──────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://36kr.com/feed",
]

WORK_KEYWORDS = [
    "融资", "创业", "IPO", "上市", "AI", "人工智能", "芯片", "半导体",
    "SaaS", "云计算", "大模型", "GPT", "投资", "估值", "营收", "财报",
    "科技", "互联网", "电商", "企业", "B2B", "数字化", "自动化",
    "机器人", "新能源", "碳中和", "区块链", "Web3",
]

CST = timezone(timedelta(hours=8))
DATE_FMT = "%Y-%m-%d"

# PushPlus（微信推送，多个 token 用逗号分隔）
PUSHPLUS_TOKENS = os.environ.get("PUSHPLUS_TOKENS", "").split(",")

# 邮件推送
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")


def fetch_rss(url: str) -> str:
    headers = {"User-Agent": "CloudNewsBot/1.0"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", unescape(text))
    return clean.strip()


def summarize(text: str, max_len: int = 30) -> str:
    text = strip_html(text)
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def classify(title: str, description: str) -> str:
    combined = f"{title} {description}"
    for kw in WORK_KEYWORDS:
        if kw in combined:
            return "work"
    return "life"


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
        items.append({"title": title, "link": link, "description": desc})

    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", "", ns) or "").strip()
            items.append({"title": title, "link": link, "description": desc})

    return items


def build_html(work_items: list[dict], life_items: list[dict], today: str) -> str:
    html = f"""<h1 style="color:#333;">{today} 今日简报</h1>
<p style="color:#888;">自动生成于 {datetime.now(CST).strftime('%H:%M')} CST</p><hr>"""

    if work_items:
        html += '<h2 style="color:#e67e22;">工作</h2>'
        for item in work_items:
            title = item["title"] or "无标题"
            summary = summarize(item["description"])
            link = item["link"]
            html += f'''<div style="margin-bottom:12px;padding:10px;background:#fef9e7;border-left:4px solid #e67e22;">
<strong>{title}</strong><br>
<span style="color:#666;">{summary}</span><br>'''
            if link:
                html += f'<a href="{link}">阅读原文</a>'
            html += '</div>'

    if life_items:
        html += '<h2 style="color:#27ae60;">生活</h2>'
        for item in life_items:
            title = item["title"] or "无标题"
            summary = summarize(item["description"])
            link = item["link"]
            html += f'''<div style="margin-bottom:12px;padding:10px;background:#eafaf1;border-left:4px solid #27ae60;">
<strong>{title}</strong><br>
<span style="color:#666;">{summary}</span><br>'''
            if link:
                html += f'<a href="{link}">阅读原文</a>'
            html += '</div>'

    if not work_items and not life_items:
        html += '<p style="color:#e74c3c;">今日未抓取到任何新闻</p>'

    html += f'<hr><p style="color:#aaa;font-size:12px;">由 GitHub Actions 自动生成 | {today}</p>'
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


def main():
    today = datetime.now(CST).strftime(DATE_FMT)
    work_items = []
    life_items = []

    for feed_url in RSS_FEEDS:
        print(f"[INFO] 抓取 RSS: {feed_url}")
        try:
            xml_text = fetch_rss(feed_url)
        except (URLError, OSError) as e:
            print(f"[ERROR] 抓取失败: {e}")
            continue

        items = parse_feed(xml_text)
        print(f"[INFO] 解析到 {len(items)} 条新闻")

        for item in items:
            cat = classify(item["title"], item["description"])
            if cat == "work":
                work_items.append(item)
            else:
                life_items.append(item)

    print(f"[INFO] 工作: {len(work_items)} 条, 生活: {len(life_items)} 条")

    title = f"{today} 今日简报"
    html_content = build_html(work_items, life_items, today)
    push_wechat(title, html_content)
    send_email(title, html_content)


if __name__ == "__main__":
    main()
