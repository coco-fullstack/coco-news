---
title: AI Agent支付赛道
date: 2026-02-18
tags:
  - research/sector
  - research/thesis
  - learning/ai
related:
  - "[[AI Agent]]"
  - "[[Crypto x AI 全景]]"
  - "[[DeFAI]]"
  - "[[交易思维：概率vs确定性]]"
status: active
---

## 核心观点

感觉 [[AI Agent]] 支付赛道要起来了。这可能是 Crypto x AI 里**最刚需**的一环。

## 为什么看好

- Agent 要自主完成任务，就必须能自主花钱（调 API、买数据、付 gas）
- 传统支付需要 KYC、银行账户 — Agent 没有身份，用不了
- 加密支付天然适合：无许可、可编程、7x24、跨境无摩擦
- Agent-to-Agent 经济：Agent 之间互相调用服务并结算，只有 crypto 能做

## 市场想象

```
今天：人用钱包付钱
明天：Agent 用钱包付钱
后天：Agent 有自己的钱包、自己赚钱、自己花钱
```

如果每个 Agent 都需要一个"支付账户"，这个市场规模 = Agent 数量 × 平均交易额。

## 关注的方向

| 方向 | 做什么 | 项目 |
|------|--------|------|
| 稳定币支付 | Agent 用 USDC/USDT 支付 | Circle, Stripe crypto |
| 微支付 | 小额高频的 Agent 间结算 | Lightning, L2 |
| 支付协议 | Agent 专用的支付标准 | 待研究 |
| 钱包基础设施 | Agent 安全持有和管理资金 | MPC 钱包, AA 钱包 |

## 关键假设 & 风险

- **假设**：Agent 会大规模普及 → 如果 Agent 只是 hype 呢？
- **假设**：Agent 需要链上支付 → 如果中心化方案够用呢？
- **风险**：监管不确定性，Agent 自主交易的法律地位
- **风险**：安全问题，Agent 被利用来洗钱或进行恶意交易

## 待研究

- [ ] 有哪些项目在做 AI Agent 支付
- [ ] 跟传统支付网关（Stripe, PayPal）的对比
- [ ] 微支付方案对比（Lightning vs L2 vs 状态通道）
- [ ] Agent 钱包的安全方案
- [ ] 市场规模预估模型
