---
title: DeFAI
date: 2026-02-18
tags:
  - research/sector
  - research/thesis
  - learning/ai
related:
  - "[[AI Agent]]"
  - "[[AI Agent支付赛道]]"
  - "[[Crypto x AI 全景]]"
status: seed
---

## 概述

DeFAI = DeFi + AI。用 [[AI Agent]] 来执行链上 DeFi 操作，降低 DeFi 的使用门槛，从"手动操作"进化到"自然语言指令"。

## 核心逻辑

- **痛点**：DeFi 操作复杂，普通用户很难跨链、找最优路由、管理仓位
- **解法**：AI Agent 做中间层，用户说"帮我在收益最高的池子里放 1 ETH"，Agent 自动执行
- **护城河**：谁能做到最安全、最智能的链上执行

## 分类

| 类型 | 做什么 | 代表项目 |
|------|--------|----------|
| 交易 Agent | 自动交易、套利、跟单 | AIXBT, Griffain |
| 收益优化 | 自动找最优 yield | 待研究 |
| 仓位管理 | 风控、再平衡 | 待研究 |
| 意图执行 | 解析用户意图并执行 | Griffain, Wayfinder |

## 风险

- 智能合约交互风险：Agent 调错合约 = 资金丢失
- 私钥安全：Agent 持有私钥的安全方案
- MEV 问题：Agent 交易容易被夹
- 过度信任：用户可能盲目信任 Agent 的判断

## 我的判断

- **看法**：看好，但还早期
- **理由**：DeFi 确实需要更好的 UX，AI Agent 是最自然的解法
- **策略**：关注有真实用户量的项目，而非纯叙事

## 待研究

- [ ] DeFAI 项目横向对比
- [ ] 链上 Agent 的安全方案（MPC、TEE、Account Abstraction）
- [ ] 真实 TVL 和用户数据
