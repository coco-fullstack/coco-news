"""
cloud_news.py - 云端新闻抓取脚本
每日定时抓取 RSS 源，按"工作/生活"分流，生成 Obsidian 手机适配版简报。
"""

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import unescape

# ── 配置 ──────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://36kr.com/feed",
    # 可在此添加更多 RSS 源
]

# 关键词分流：匹配到"工作"关键词的归入工作，其余归入生活
WORK_KEYWORDS = [
    "融资", "创业", "IPO", "上市", "AI", "人工智能", "芯片", "半导体",
    "SaaS", "云计算", "大模型", "GPT", "投资", "估值", "营收", "财报",
    "科技", "互联网", "电商", "企业", "B2B", "数字化", "自动化",
    "机器人", "新能源", "碳中和", "区块链", "Web3",
]

# 输出路径模板（Obsidian vault 内）
OUTPUT_DIR = "每日热点新闻"
DATE_FMT = "%Y-%m-%d"

# 东八区
CST = timezone(timedelta(hours=8))


def fetch_rss(url: str) -> str:
    """抓取 RSS XML 内容。"""
    headers = {"User-Agent": "CloudNewsBot/1.0"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    """去除 HTML 标签，返回纯文本。"""
    clean = re.sub(r"<[^>]+>", "", unescape(text))
    return clean.strip()


def summarize(text: str, max_len: int = 30) -> str:
    """截取前 max_len 个字符作为摘要。"""
    text = strip_html(text)
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def classify(title: str, description: str) -> str:
    """根据标题和描述中的关键词判断分类。"""
    combined = f"{title} {description}"
    for kw in WORK_KEYWORDS:
        if kw in combined:
            return "work"
    return "life"


def parse_feed(xml_text: str) -> list[dict]:
    """解析 RSS XML，返回条目列表。"""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        print("[WARN] RSS XML 解析失败，跳过")
        return items

    # 支持 RSS 2.0 (<item>) 和 Atom (<entry>)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # RSS 2.0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        items.append({"title": title, "link": link, "description": desc})

    # Atom
    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", "", ns) or "").strip()
            items.append({"title": title, "link": link, "description": desc})

    return items


def build_markdown(work_items: list[dict], life_items: list[dict], today: str) -> str:
    """生成 Obsidian 手机端优化的 Markdown 简报。"""
    lines = [
        f"# {today} 今日简报",
        "",
        f"> [!info] 自动生成于 {datetime.now(CST).strftime('%H:%M')} CST",
        "",
    ]

    if work_items:
        lines.append("## 工作")
        lines.append("")
        for item in work_items:
            title = item["title"] or "无标题"
            summary = summarize(item["description"])
            link = item["link"]
            lines.append(f"> [!tip] {title}")
            lines.append(f"> {summary}")
            if link:
                lines.append(f"> [阅读原文]({link})")
            lines.append("")

    if life_items:
        lines.append("## 生活")
        lines.append("")
        for item in life_items:
            title = item["title"] or "无标题"
            summary = summarize(item["description"])
            link = item["link"]
            lines.append(f"> [!note] {title}")
            lines.append(f"> {summary}")
            if link:
                lines.append(f"> [阅读原文]({link})")
            lines.append("")

    if not work_items and not life_items:
        lines.append("> [!warning] 今日未抓取到任何新闻")
        lines.append("")

    lines.append("---")
    lines.append(f"*由 GitHub Actions 自动生成 | {today}*")
    lines.append("")

    return "\n".join(lines)


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

    md_content = build_markdown(work_items, life_items, today)

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"{today}_今日简报.md")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"[OK] 简报已生成: {output_file}")


if __name__ == "__main__":
    main()
