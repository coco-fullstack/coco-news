---
title: 知识库首页
date: 2026-02-18
tags: []
---

# 知识库导航

> 切换到**阅读模式**（Ctrl+E）查看自动汇总

---

## 币种研究一览

```dataview
TABLE
  tags as "标签",
  status as "状态"
FROM "投资交易/研究"
WHERE contains(tags, "research/token")
SORT date DESC
```

## 最近修改的笔记

```dataview
TABLE dateformat(file.mtime, "yyyy-MM-dd HH:mm") as "修改时间"
FROM ""
WHERE !contains(file.path, "模板") AND !contains(file.path, "杂七杂八") AND file.name != "HOME"
SORT file.mtime DESC
LIMIT 10
```

## 所有待办事项

```dataview
TASK
FROM ""
WHERE !completed
LIMIT 20
```

## 最近日记

```dataview
LIST
FROM "日记"
SORT date DESC
LIMIT 7
```

---

## 快速入口

### 投资交易
- **研究**：[[Crypto x AI 全景]] / [[AI Agent]] / [[DeFAI]] / [[KITE AI]] / [[SkyAI]]
- **策略**：[[趋势交易策略]] / [[交易系统checklist]]
- **思考**：[[我的投资原则]] / [[交易思维：概率vs确定性]] / [[牛熊周期思考]] / [[AI Agent支付赛道]]

### 其他
- [[阅读书单]] / [[学习方法论]]
- [[想法收集]] / [[有意思的点子]]
- [[旅行愿望清单]] / [[想买的东西]] / [[长期规划]]
- [[常用指令]]

---

```
coco/
├── 日记/              ← 有想法时记录
├── 投资交易/
│   ├── 研究/          ← 赛道、项目调研
│   ├── 策略/          ← 交易系统
│   └── 思考/          ← 投资感悟
├── 学习/（书单 + 思考）
├── 灵感/              ← 随手记
├── coco的旅行日记/
├── buy/
├── 未来！/            ← 长期规划
├── 模板/
├── 收件箱/
├── 杂七杂八/
└── 归档/
```
