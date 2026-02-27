"""
sync_to_google.py - 灵感自动上云脚本
监测 Git Push 变更的 Markdown 文件，提取金句（> 开头），
增量追加到 Google Docs 文档，供 NotebookLM 使用。
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── 配置 ──────────────────────────────────────────────────────────
# Google Docs 文档 ID（从 URL 中获取）
# URL 格式: https://docs.google.com/document/d/{DOCUMENT_ID}/edit
GOOGLE_DOC_ID = os.environ.get("GOOGLE_DOC_ID", "YOUR_DOCUMENT_ID_HERE")

# Google Service Account 凭据（JSON 字符串，存在 GitHub Secrets 中）
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS", "")

# 东八区
CST = timezone(timedelta(hours=8))

# Scopes
SCOPES = ["https://www.googleapis.com/auth/documents"]


def get_changed_md_files() -> list[str]:
    """获取本次 Push 中变更的 Markdown 文件列表。"""
    # 获取最近一次 push 前后的 commit 范围
    before_sha = os.environ.get("BEFORE_SHA", "")
    after_sha = os.environ.get("AFTER_SHA", "HEAD")

    if before_sha:
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", before_sha, after_sha]
    else:
        # fallback: 对比上一次 commit
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD~1", "HEAD"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        files = result.stdout.strip().split("\n")
        return [f for f in files if f.endswith(".md") and f.strip()]
    except subprocess.CalledProcessError as e:
        print(f"[WARN] git diff 失败: {e}")
        return []


def extract_quotes(filepath: str) -> list[str]:
    """从 Markdown 文件中提取所有以 '> ' 开头的金句。"""
    quotes = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                # 匹配 > 开头的引用行（排除 Callout 语法如 > [!info]）
                if re.match(r"^>\s+(?!\[!)", line):
                    text = line.lstrip(">").strip()
                    if text and len(text) >= 4:  # 过滤太短的内容
                        quotes.append(text)
    except FileNotFoundError:
        print(f"[WARN] 文件不存在: {filepath}")
    return quotes


def get_docs_service():
    """创建 Google Docs API 服务实例。"""
    if not GOOGLE_CREDENTIALS_JSON:
        raise RuntimeError("GOOGLE_CREDENTIALS 环境变量未设置")

    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build("docs", "v1", credentials=creds)


def append_to_doc(service, doc_id: str, quotes: list[str], source_files: list[str]):
    """将金句增量追加到 Google Docs 文档末尾。"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    separator = f"\n{'='*50}\n"
    header = f"  同步时间: {now} CST\n"
    sources = f"  来源文件: {', '.join(source_files)}\n\n"

    text_to_append = separator + header + sources
    for i, q in enumerate(quotes, 1):
        text_to_append += f"  {i}. {q}\n"
    text_to_append += "\n"

    # 获取文档当前末尾位置
    doc = service.documents().get(documentId=doc_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])
    end_index = content[-1]["endIndex"] - 1 if content else 1

    # 构建插入请求
    requests = [
        {
            "insertText": {
                "location": {"index": end_index},
                "text": text_to_append,
            }
        }
    ]

    service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    print(f"[OK] 已追加 {len(quotes)} 条金句到 Google Doc")


def main():
    print("[INFO] 开始扫描变更文件...")

    changed_files = get_changed_md_files()
    if not changed_files:
        print("[INFO] 没有变更的 Markdown 文件，跳过")
        return

    print(f"[INFO] 发现 {len(changed_files)} 个变更文件: {changed_files}")

    all_quotes = []
    source_files = []

    for filepath in changed_files:
        quotes = extract_quotes(filepath)
        if quotes:
            all_quotes.extend(quotes)
            source_files.append(filepath)
            print(f"[INFO] {filepath}: 提取 {len(quotes)} 条金句")

    if not all_quotes:
        print("[INFO] 未提取到金句，跳过同步")
        return

    print(f"[INFO] 共提取 {len(all_quotes)} 条金句，准备同步到 Google Docs...")

    service = get_docs_service()
    append_to_doc(service, GOOGLE_DOC_ID, all_quotes, source_files)

    print("[OK] 同步完成!")


if __name__ == "__main__":
    main()
