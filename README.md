<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Vercel-Deployed-black?logo=vercel" alt="Vercel"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
  <img src="https://img.shields.io/github/last-commit/coco0327/training-webapp" alt="Last Commit"/>
</p>

<h1 align="center">CoCo Toolkit</h1>

<p align="center">
  个人学习项目集合 &nbsp;|&nbsp; 個人学習プロジェクト集 &nbsp;|&nbsp; Personal Learning Projects
</p>

---

## CN | 中文

一个用于**学习和实践**的项目仓库，包含两个独立模块：

### 1. CineVerse — 影视聚合浏览器

基于 Vercel Serverless 部署的影视信息聚合工具，无需 API Key。

- 电影 / 电视剧 / 动漫 信息浏览
- 数据源：TMDB 公开页面 + Jikan API (MyAnimeList)
- 支持 HLS 流媒体播放
- 纯前端 + Python Serverless，零依赖

### 2. Crypto Market Push — 加密市场智能推送

通过 GitHub Actions 定时运行的加密货币行情监控与推送系统。

- **每日晨报**：宏观流动性 + 机构指标 + 衍生品数据 + AI 摘要
- **即时预警**：价格异动 / 极端情绪 / 资金费率异常 / 大额清算
- **周报总结**：每周日自动生成
- 推送渠道：邮件 (Gmail SMTP) + PushPlus 微信推送
- 数据源：CoinGecko / Binance / CoinPaprika / Alternative.me

### 项目结构

```
├── api/              # Vercel Serverless 函数
├── public/           # CineVerse 前端页面
├── front/            # 流媒体播放页面
├── scripts/          # 市场推送脚本
├── data/             # 行情快照 & 缓存
└── .github/workflows # 定时任务 (晨报/预警/周报)
```

### 快速开始

```bash
# CineVerse — 本地开发
python scripts/movie_server.py    # 访问 http://localhost:8080

# 市场推送 — 手动触发
python scripts/cloud_news.py daily   # 晨报
python scripts/cloud_news.py alert   # 预警
```

环境变量（GitHub Secrets 或本地 export）：

| 变量 | 用途 |
|---|---|
| `SMTP_USER` / `SMTP_PASS` | Gmail SMTP 发件 |
| `EMAIL_TO` | 收件邮箱（逗号分隔） |
| `PUSHPLUS_TOKENS` | PushPlus 微信推送 Token |
| `GROQ_API_KEY` | AI 摘要（Groq） |
| `GEMINI_API_KEY` | AI 摘要备用（Gemini） |

---

## JP | 日本語

**学習・練習用**のプロジェクトリポジトリです。2つの独立モジュールを含みます：

### 1. CineVerse — 映画・アニメ情報ブラウザ

Vercel Serverless で動作する映像情報アグリゲーター。API キー不要。

- 映画 / ドラマ / アニメ の情報閲覧
- データソース：TMDB + Jikan API (MyAnimeList)
- HLS ストリーミング対応
- フロントエンド + Python Serverless、外部依存なし

### 2. Crypto Market Push — 暗号資産マーケット通知

GitHub Actions で定期実行する暗号資産モニタリング＆プッシュ通知システム。

- **日次レポート**：マクロ流動性 + 機関投資家指標 + デリバティブ + AI サマリー
- **即時アラート**：価格急変 / 極端なセンチメント / ファンディングレート異常
- **週次レポート**：毎週日曜に自動生成
- 通知チャネル：メール (Gmail SMTP) + PushPlus (WeChat)

---

## EN | English

A personal **learning and practice** repository containing two independent modules:

### 1. CineVerse — Movie & Anime Browser

A movie/TV/anime information aggregator deployed on Vercel Serverless. No API key required.

- Browse movies, TV shows, and anime
- Data sources: TMDB public pages + Jikan API (MyAnimeList)
- HLS streaming support
- Pure frontend + Python serverless, zero dependencies

### 2. Crypto Market Push — Market Intelligence System

A cryptocurrency market monitoring and push notification system powered by GitHub Actions.

- **Daily Digest**: Macro liquidity + institutional metrics + derivatives + AI summary
- **Instant Alerts**: Price spikes / extreme sentiment / funding rate anomalies
- **Weekly Report**: Auto-generated every Sunday
- Channels: Email (Gmail SMTP) + PushPlus (WeChat)

### Quick Start

```bash
# CineVerse — Local dev
python scripts/movie_server.py    # Visit http://localhost:8080

# Market Push — Manual trigger
python scripts/cloud_news.py daily   # Daily digest
python scripts/cloud_news.py alert   # Alert check
```

---

## License

MIT

---

> Built for learning. Not for production use.
