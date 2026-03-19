"""生成邮件模板预览 HTML（mock 数据）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from cloud_news import build_daily_html, build_alert_html, trend_label

mock_data = {
    "prices": {
        "BTC": {"price": 83542.0, "change": 2.3},
        "ETH": {"price": 1925.4, "change": -1.8},
        "SOL": {"price": 128.5, "change": 5.7},
        "BNB": {"price": 598.2, "change": 0.4},
        "XRP": {"price": 2.34, "change": -3.1},
        "DOGE": {"price": 0.165, "change": 8.2},
        "ADA": {"price": 0.72, "change": -0.5},
    },
    "fng": {"value": 32, "label": "恐惧"},
    "trend_score": 58,
    "stablecoins": {
        "USDT": {"mcap": 143_500_000_000, "mcap_change_pct": 0.12},
        "USDC": {"mcap": 52_300_000_000, "mcap_change_pct": -0.05},
    },
    "global": {
        "total_market_cap": 2_850_000_000_000,
        "btc_dominance": 61.2,
    },
    "funding": {"BTC": 0.0102, "ETH": 0.0045, "SOL": -0.0031},
    "btc_rsi": 44.5,
    "eth_rsi": 38.2,
    "long_short": {
        "BTC": {"long_pct": 52.3},
        "ETH": {"long_pct": 68.5},
    },
    "gas_fee": {"standard": 12, "fast": 18},
    "liquidations": {
        "total_24h": 235_000_000,
        "long_ratio": 62.0,
    },
    "coin_liquidations": {
        "BTC": {
            "oi_value_usd": 32_500_000_000,
            "oi_change_pct": 3.2,
            "buy_sell_ratio": 1.05,
            "long_ratio": 51.8,
        },
        "ETH": {
            "oi_value_usd": 12_800_000_000,
            "oi_change_pct": -2.1,
            "buy_sell_ratio": 0.88,
            "long_ratio": 46.3,
        },
    },
    "yields": {
        "US10Y": {"value": 4.32, "prev": 4.28},
        "JP10Y": {"value": 1.58, "prev": 1.55},
    },
    "forex": {"USD/JPY": 149.82, "USD/CNY": 7.24, "100JPY/CNY": 4.33},
    "defi_tvl": {"total_tvl": 95_200_000_000, "change_pct": 1.8},
    "options_expiry": {
        "BTC": [
            {"date_fmt": "03/21", "days_left": 3, "notional_usd": 8_500_000_000, "oi_coins": 101500, "is_major": True, "max_pain": 85000},
            {"date_fmt": "03/28", "days_left": 10, "notional_usd": 3_200_000_000, "oi_coins": 38200, "is_major": False, "max_pain": 82000},
        ],
        "ETH": [
            {"date_fmt": "03/21", "days_left": 3, "notional_usd": 2_100_000_000, "oi_coins": 1090000, "is_major": True, "max_pain": 1950},
        ],
    },
    "institutional": {
        "BTC": {
            "total_value_usd": 85_000_000_000,
            "top_companies": [
                {"name": "MicroStrategy", "value_usd": 42_000_000_000, "pct_supply": 2.38},
                {"name": "BlackRock iShares", "value_usd": 18_500_000_000, "pct_supply": 1.05},
                {"name": "Fidelity", "value_usd": 12_000_000_000, "pct_supply": 0.68},
                {"name": "Grayscale", "value_usd": 8_200_000_000, "pct_supply": 0.46},
                {"name": "ARK Invest", "value_usd": 4_300_000_000, "pct_supply": 0.24},
            ],
        },
    },
    "ai_summary": "BTC 在 83K 附近震荡整理，ETH 相对偏弱，ETH/BTC 汇率持续走低。<br>· 期权市场：本周五 BTC 85亿美元期权到期，为重大交割日，需关注 pin 风险<br>· 资金费率中性偏低，做多热情有限<br>· 恐贪指数回落至恐惧区间，短期市场情绪偏谨慎<br>· 建议：观望为主，关注 83K 支撑和 85K 阻力位",
    "ai_engine": "Gemini",
    "strategy_indicators": {
        "BTC": {
            "price": 83542.0,
            "ma7": 83200, "ma25": 82500, "ma50": 80100,
            "ma_signal": "偏多", "ma_class": "g",
            "macd_signal": "死叉", "macd_class": "r",
            "macd_dif": -120.5, "macd_dea": -85.3, "macd_hist": -70.4,
            "vol_signal": "缩量", "vol_class": "b", "vol_change": -18, "vol_7d_avg": 28_500_000_000,
            "support": 79800, "resistance": 88500, "price_vs_range": 43,
            "funding_trend": "平稳", "funding_trend_class": "b",
            "funding_rates": [0.0095, 0.0102, 0.0098],
        },
        "ETH": {
            "price": 1925.4,
            "ma7": 1940, "ma25": 1980, "ma50": 2050,
            "ma_signal": "空头排列", "ma_class": "r",
            "macd_signal": "死叉+绿柱", "macd_class": "r",
            "macd_dif": -28.5, "macd_dea": -15.2, "macd_hist": -26.6,
            "vol_signal": "温和放量", "vol_class": "y", "vol_change": 15, "vol_7d_avg": 12_800_000_000,
            "support": 1820, "resistance": 2150, "price_vs_range": 32,
            "funding_trend": "下降", "funding_trend_class": "g",
            "funding_rates": [0.0065, 0.0045, 0.0028],
        },
    },
    "ai_strategy": "BTC 技术面偏中性，MACD 空头收敛暗示短期可能变盘。<br>ETH 相对弱势，MA20 下方运行，建议等待企稳信号。<br>策略建议：轻仓观望，BTC 82K-85K 区间等待方向选择。",
    "ai_strategy_engine": "Gemini",
    "screening": {
        "btc_benchmark": {"7d": 3.2, "30d": -5.1, "1y": 62.5},
        "binance_count": 380,
        "total_coins": 200,
        "outperformers": {
            "7d": [
                {"symbol": "PENDLE", "rank": 85, "change": 28.5, "vs_btc": 25.3, "binance": True},
                {"symbol": "FET", "rank": 62, "change": 18.2, "vs_btc": 15.0, "binance": True},
                {"symbol": "RENDER", "rank": 45, "change": 15.8, "vs_btc": 12.6, "binance": True},
            ],
        },
    },
    "watchlist_news": {
        "SOL": [
            {"title": "Solana DEX volume hits new ATH", "title_cn": "Solana DEX 交易量创历史新高", "source": "The Block", "link": "https://example.com/1"},
        ],
    },
    "news": [
        {"title": "Fed maintains rates", "title_cn": "美联储维持利率不变，鲍威尔暗示年内或降息两次", "source": "Reuters", "link": "https://example.com/2", "urgent": True},
        {"title": "BlackRock BTC ETF inflow", "title_cn": "贝莱德 BTC ETF 单日净流入 $4.2亿", "source": "Bloomberg", "link": "https://example.com/3", "urgent": False},
        {"title": "Ethereum Pectra upgrade", "title_cn": "以太坊 Pectra 升级测试网进展顺利，预计Q2上线", "source": "CoinDesk", "link": "https://example.com/4", "urgent": False},
        {"title": "Binance lists new tokens", "title_cn": "Binance 上线新交易对，市场关注 Launchpool 新项目", "source": "Binance", "link": "https://example.com/5", "urgent": False},
        {"title": "MicroStrategy buys more BTC", "title_cn": "MicroStrategy 再次增持 1,200 BTC，总持仓突破 50 万枚", "source": "SEC Filing", "link": "https://example.com/6", "urgent": True},
    ],
}

# 生成 Daily HTML
daily_html = build_daily_html(mock_data)
out_daily = os.path.join(os.path.dirname(__file__), "preview_daily.html")
with open(out_daily, "w", encoding="utf-8") as f:
    f.write(daily_html)
print(f"Daily preview: {out_daily}")

# 生成 Alert HTML
alert_html = build_alert_html([
    {
        "title": "价格异动",
        "danger": True,
        "items": [
            "BTC 1h 急跌 -4.2%，当前 $83,542，触发价格异动预警",
            "ETH 跟随下跌 -3.8%，关注 $1,900 支撑位",
        ],
    },
    {
        "title": "资金费率异常",
        "danger": False,
        "items": [
            "SOL 资金费率 -0.0031%，处于过冷区间，空头拥挤",
            "BTC 资金费率 0.0102%，接近过热阈值",
        ],
    },
])
out_alert = os.path.join(os.path.dirname(__file__), "preview_alert.html")
with open(out_alert, "w", encoding="utf-8") as f:
    f.write(alert_html)
print(f"Alert preview: {out_alert}")
