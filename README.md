<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/GitHub_Actions-Automated-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
  <img src="https://img.shields.io/github/last-commit/coco0327/training-webapp" alt="Last Commit"/>
</p>

<h1 align="center">Crypto Market Push</h1>

<p align="center">
  加密市场智能推送 &nbsp;|&nbsp; 暗号資産マーケット通知 &nbsp;|&nbsp; Crypto Market Intelligence
</p>

---

## CN | 中文

通过 GitHub Actions 定时运行的加密货币行情监控与推送系统。零服务器成本，全自动运行。

### 功能

- **每日晨报** — 宏观流动性 + 机构指标 + 衍生品数据 + AI 摘要 + 决策参考
- **即时预警** — 价格异动 / 极端情绪 / 资金费率异常 / 大额清算（每 4 小时检查）
- **紧急新闻** — 重大事件即时推送（每 2 小时检查）
- **周报总结** — 每周日自动生成周度回顾

### 数据源

CoinGecko / Binance / CoinPaprika / Alternative.me / FRED

### 推送渠道

邮件 (Gmail SMTP) + PushPlus 微信推送

### 项目结构

```
├── scripts/
│   ├── cloud_news.py       # 核心推送引擎（晨报/预警/紧急/周报）
│   └── preview_email.py    # 邮件模板本地预览
├── data/
│   ├── snapshots/          # 每日行情快照（自动归档）
│   └── cache/              # 机构持仓等缓存数据
└── .github/workflows/
    ├── main.yml            # 每日晨报 + 4h 预警
    ├── urgent.yml          # 2h 紧急新闻检查
    └── weekly.yml          # 周日周报
```

### 快速开始

```bash
# 手动触发
python scripts/cloud_news.py daily   # 晨报
python scripts/cloud_news.py alert   # 预警
python scripts/cloud_news.py urgent  # 紧急检查
python scripts/cloud_news.py weekly  # 周报

# 预览邮件模板
python scripts/preview_email.py
```

### 环境变量

通过 GitHub Secrets 配置，本地开发时 `export` 即可：

| 变量 | 用途 |
|---|---|
| `SMTP_USER` / `SMTP_PASS` | Gmail SMTP 发件凭据 |
| `EMAIL_TO` | 收件邮箱（逗号分隔多个） |
| `PUSHPLUS_TOKENS` | PushPlus 微信推送 Token |
| `GROQ_API_KEY` | AI 摘要生成（Groq） |
| `GEMINI_API_KEY` | AI 摘要备用（Gemini） |
| `FRED_API_KEY` | 美联储经济数据 |

---

## JP | 日本語

GitHub Actions で定期実行する暗号資産モニタリング＆プッシュ通知システム。サーバー不要、完全自動。

### 機能

- **日次レポート** — マクロ流動性 + 機関投資家指標 + デリバティブ + AI サマリー + 投資判断参考
- **即時アラート** — 価格急変 / 極端なセンチメント / ファンディングレート異常（4時間毎）
- **緊急ニュース** — 重大イベントの即時通知（2時間毎）
- **週次レポート** — 毎週日曜に自動生成

### データソース

CoinGecko / Binance / CoinPaprika / Alternative.me / FRED

### 通知チャネル

メール (Gmail SMTP) + PushPlus (WeChat)

---

## EN | English

A cryptocurrency market monitoring and push notification system powered by GitHub Actions. Zero server cost, fully automated.

### Features

- **Daily Digest** — Macro liquidity + institutional metrics + derivatives + AI summary
- **Instant Alerts** — Price spikes / extreme sentiment / funding rate anomalies (every 4h)
- **Urgent News** — Breaking events push (every 2h)
- **Weekly Report** — Auto-generated every Sunday

### Data Sources

CoinGecko / Binance / CoinPaprika / Alternative.me / FRED

### Notification Channels

Email (Gmail SMTP) + PushPlus (WeChat)

### Quick Start

```bash
python scripts/cloud_news.py daily   # Daily digest
python scripts/cloud_news.py alert   # Alert check
python scripts/cloud_news.py urgent  # Urgent news
python scripts/cloud_news.py weekly  # Weekly report
```

---

## License

MIT

---

> Built for learning purposes.
