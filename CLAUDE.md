# CLAUDE.md — Vault 管理指南

> 本文件为 AI 助手提供操作本知识库的完整指引。

## 项目概览

这是一个 **Obsidian 风格的个人知识库（Vault）**，内容聚焦加密货币交易、Crypto x AI 赛道研究和个人学习。所有笔记使用中文撰写，标签使用英文。知识库通过 Git 进行版本管理。

**工具链**：Obsidian / 任意 Markdown 编辑器 + Git

---

## 文件夹结构

```
coco/
├── CLAUDE.md        # 本文件 — AI 助手指引
├── HOME.md          # 知识库导航页（笔记索引 + 关系图）
├── Inbox/           # 未整理的原始想法（整理后清空）
├── Trading/         # 交易相关：策略、复盘、交易日志
├── Research/        # 项目调研：token 分析、赛道研究
├── Learning/        # 学习笔记：书单、课程、技术
├── Thoughts/        # 个人思考：投资论点、框架、随想
├── Templates/       # 模板文件（6 个标准模板）
└── Archive/         # 已归档的旧笔记
```

### 当前内容

| 文件夹 | 文件数 | 主要内容 |
|--------|--------|----------|
| Research/ | 3 | AI Agent、DeFAI、Crypto x AI 全景 |
| Trading/ | 2 | 趋势交易策略、交易系统 checklist |
| Thoughts/ | 3 | 概率思维、牛熊周期、AI Agent 支付赛道 |
| Learning/ | 1 | 阅读书单 |
| Templates/ | 6 | 交易日志/策略/日记、赛道/币种研究、读书笔记 |

---

## Frontmatter 规范

每篇笔记 **必须** 包含以下 YAML frontmatter：

```yaml
---
title: 笔记标题
date: YYYY-MM-DD
tags:
  - 主分类标签
  - 可选的次分类标签
related:
  - "[[相关笔记1]]"
  - "[[相关笔记2]]"
status: seed | draft | active
---
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `title` | 是 | 笔记标题，与文件名一致 |
| `date` | 是 | 创建日期，格式 `YYYY-MM-DD` |
| `tags` | 是 | 标签数组，使用下方标签体系 |
| `related` | 是 | 相关笔记双向链接数组，可为空 `[]` |
| `status` | 是 | `seed`（萌芽）/ `draft`（草稿）/ `active`（完善） |

### 模板变量

Templates/ 中的模板使用 `{{title}}` 和 `{{date}}` 作为占位符，创建新笔记时需替换为实际值。

---

## 标签体系

标签统一使用 **英文小写**，采用 `分类/子类` 的层级格式：

### 交易
- `trading/strategy` — 交易策略
- `trading/journal` — 交易日志
- `trading/review` — 交易复盘

### 研究
- `research/token` — 单个 token/项目分析
- `research/sector` — 赛道研究
- `research/thesis` — 投资论点

### 学习
- `learning/quant` — 量化相关
- `learning/coding` — 编程相关
- `learning/ai` — AI 相关

### 币种标签
- `token/BTC`, `token/ETH`, `token/VIRTUAL` 等
- 笔记中提到具体币种时，添加对应 `token/xxx` 标签

一篇笔记可以有多个标签（如 `research/sector` + `learning/ai`）。

---

## 双向链接规范

使用 Obsidian 标准的 `[[双括号]]` 语法建立笔记间关联：

- 正文中提到其他笔记主题时，使用 `[[笔记名]]` 链接
- 同时在 frontmatter 的 `related` 字段中记录，格式为 `"[[笔记名]]"`
- 识别文中提到的概念、币种、项目名，主动添加链接
- HOME.md 作为导航中枢，应包含所有重要笔记的链接

---

## Inbox 整理规则

这是本知识库的核心工作流。当用户要求整理笔记时，按以下步骤操作：

1. **读取** `Inbox/` 中的所有文件
2. **分类** 根据内容判断归属文件夹：
   - 交易相关 → `Trading/`
   - 调研分析 → `Research/`
   - 学习笔记 → `Learning/`
   - 短想法/随感 → `Thoughts/`
3. **添加 frontmatter** 按上述规范补充完整的元数据
4. **建立链接** 识别文中的概念、币种、项目名，添加 `[[]]` 双向链接
5. **移动文件** 将笔记移至目标文件夹，删除 Inbox 中的原始文件
6. **更新 HOME.md** 如有新增重要笔记，添加到导航页对应分类下

### 特殊处理

| 情况 | 处理方式 |
|------|----------|
| URL 链接 | 提取标题和描述，生成摘要笔记 |
| 很短的内容（< 3 句） | 补充 frontmatter 后放入 `Thoughts/` |
| 涉及具体币种 | 添加 `token/xxx` 标签 |
| 无法明确分类 | 放入 `Thoughts/`，标记 `status: seed` |

---

## 写作规范

- **笔记正文**：使用中文
- **标签**：使用英文小写
- **frontmatter 字段名**：使用英文
- **Markdown 格式**：使用标准 Markdown（标题、列表、表格、代码块）
- **文件命名**：中文标题，与 frontmatter 的 `title` 一致
- **文件格式**：`.md` 后缀

---

## 可用模板

创建新笔记时优先使用对应模板：

| 模板 | 用途 | 默认标签 |
|------|------|----------|
| `Templates/交易日志模板.md` | 每日交易记录 | `trading/journal` |
| `Templates/交易策略模板.md` | 策略定义与回测 | `trading/strategy` |
| `Templates/每日日记模板.md` | 日常日记 | — |
| `Templates/赛道研究模板.md` | 行业赛道分析 | `research/sector` |
| `Templates/币种研究模板.md` | 单个项目/代币分析 | `research/token` |
| `Templates/读书笔记模板.md` | 读书笔记 | — |

---

## Git 工作流

- 分支策略：`master` 为主分支
- 提交信息使用中文，简洁描述变更内容
- 示例：`"整理 Inbox 笔记，新增 3 篇研究"`、`"更新交易策略，补充回测记录"`

---

## AI 助手操作注意事项

1. **不要删除或覆盖已有笔记内容**，只做追加和元数据补充
2. **保持已有的链接关系**，只增不减
3. **整理后务必更新 HOME.md**，保持导航页同步
4. **不确定分类时放 Thoughts/**，标记 `status: seed`
5. **新建笔记时检查是否已有同主题笔记**，避免重复
6. **修改笔记时保持原有写作风格和语气**
