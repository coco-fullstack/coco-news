---
title: AI Agent
date: 2026-02-18
tags:
  - research/sector
  - learning/ai
related:
  - "[[AI Agent支付赛道]]"
  - "[[DeFAI]]"
  - "[[Crypto x AI 全景]]"
status: active
---

## 概述

AI Agent 是能够自主执行任务、做出决策的人工智能系统。与传统 AI 工具的"输入-输出"模式不同，Agent 具备**自主规划、工具调用、记忆管理和持续交互**的能力。

## 核心逻辑

- **为什么现在**：LLM 推理能力突破 → Agent 从 demo 走向生产可用
- **驱动因素**：模型能力提升、工具调用标准化（MCP）、链上基础设施成熟
- **时间窗口**：2025-2026，基础设施建设期 → 2026-2027 应用爆发期

## 技术栈分层

```
应用层    ：面向用户的 Agent 产品（交易机器人、研究助手、社交 Agent）
框架层    ：Agent 开发框架（ElizaOS, Rig, ZerePy, CrewAI）
协议层    ：Agent 通信/注册/支付协议
模型层    ：底层 LLM（GPT, Claude, Llama, 链上推理）
基础设施  ：算力、数据、存储
```

## 相关赛道

| 赛道 | 核心问题 | 笔记 |
|------|----------|------|
| 支付 | Agent 如何自主付钱 | [[AI Agent支付赛道]] |
| DeFi | Agent 如何做链上交易 | [[DeFAI]] |
| 社交 | Agent 如何与人/Agent 交互 | 待研究 |
| 基础设施 | Agent 在哪里运行 | 待研究 |

## 主要项目

| 项目 | 代币 | 定位 | 简介 |
|------|------|------|------|
| Virtuals Protocol | VIRTUAL | Agent 发射平台 | Agent tokenization，Base 链上最大的 AI Agent 平台 |
| ai16z / ElizaOS | AI16Z | 框架 + DAO | 开源 Agent 框架，DAO 治理模式 |
| Griffain | GRIFFAIN | Agent 平台 | Solana 上的 AI Agent 平台，支持自然语言操作 DeFi |
| ARC | ARC | 框架 | Rust 写的 Agent 框架（Rig），主打性能 |
| AIXBT | AIXBT | 应用 | AI 驱动的 crypto 市场分析 Agent |

## 关键问题

- Agent 的"自主性"边界在哪？完全自主 vs 人类监督
- Agent 经济模型：谁付费、如何分润、如何防止滥用
- 安全性：prompt injection、私钥管理、恶意 Agent

## 待研究

- [ ] Agent 框架对比（ElizaOS vs Rig vs ZerePy）
- [ ] [[Crypto x AI 全景]] 梳理
- [ ] Agent 通信协议（Agent-to-Agent）
- [ ] 链上推理 vs 链下推理的 tradeoff
- [ ] 各项目的代币经济模型对比
