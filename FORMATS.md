# Wiki 格式规范

本文档从 [AGENTS.md](AGENTS.md) 提取，集中描述 wiki 中所有文件/页面的格式规范，并说明每种格式的适用场景。

---

## 1. 通用 Page Format（页面格式）

**适用文件：** `wiki/` 下所有页面文件（包括 `wiki/sources/`、`wiki/entities/`、`wiki/concepts/`、`wiki/syntheses/` 下的每一篇 `.md` 页面）。

**用途：** 这是所有 wiki 页面的通用元数据头。每个页面文件开头都必须包含此 frontmatter，用于声明页面的标题、类型、标签、引用来源和更新时间。

```yaml
---
title: "Page Title"
type: source | entity | concept | synthesis
tags: []
sources: []       # list of source slugs that inform this page
last_updated: YYYY-MM-DD
---
```

`type` 字段取值说明：
- `source` — 来源文档摘要页
- `entity` — 实体页（人物、公司、项目、产品）
- `concept` — 概念页（思想、框架、方法、理论）
- `synthesis` — 综合/分析页（保存的查询回答）

正文中使用 `[[PageName]]` wikilinks 链接到其他 wiki 页面。

---

## 2. Naming Conventions（命名规范）

**适用场景：** 创建任何新的 wiki 页面文件时的文件命名规则。

| 页面类型 | 命名规则 | 示例 |
|---|---|---|
| Source slugs | `kebab-case`，与源文件名匹配 | `my-paper.md` |
| Entity pages | `TitleCase.md` | `OpenAI.md`、`SamAltman.md` |
| Concept pages | `TitleCase.md` | `ReinforcementLearning.md`、`RAG.md` |

---

## 3. Source Page Format（来源页格式）

**适用文件：** `wiki/sources/<slug>.md`

**用途：** 每摄入一份原始文档（`raw/` 目录下的文件），都应在 `wiki/sources/` 下生成一篇对应摘要页。此模板用于规范摘要页的结构。

```markdown
---
title: "Source Title"
type: source
tags: []
date: YYYY-MM-DD
source_file: raw/...
---

## Summary
2–4 sentence summary.

## Key Claims
- Claim 1
- Claim 2

## Key Quotes
> "Quote here" — context

## Connections
- [[EntityName]] — how they relate
- [[ConceptName]] — how it connects

## Contradictions
- Contradicts [[OtherPage]] on: ...
```

---

## 4. Domain-Specific Templates（特定领域模板）

当摄入的源文档属于特定领域时，应使用专用模板替代上述通用来源页格式。

### 4a. Diary / Journal Template（日记模板）

**适用文件：** `wiki/sources/<slug>.md`（当源文档为个人日记/日志时）

```markdown
---
title: "YYYY-MM-DD Diary"
type: source
tags: [diary]
date: YYYY-MM-DD
---
## Event Summary
...
## Key Decisions
...
## Energy & Mood
...
## Connections
...
## Shifts & Contradictions
...
```

### 4b. Meeting Notes Template（会议记录模板）

**适用文件：** `wiki/sources/<slug>.md`（当源文档为会议记录时）

```markdown
---
title: "Meeting Title"
type: source
tags: [meeting]
date: YYYY-MM-DD
---
## Goal
...
## Key Discussions
...
## Decisions Made
...
## Action Items
...
```

---

## 5. Index Format（索引格式）

**适用文件：** `wiki/index.md`

**用途：** `wiki/index.md` 是整个 wiki 的目录/索引页，记录所有 wiki 页面的清单。每次完成 ingest 操作后都需要更新此文件。

```markdown
# Wiki Index

## Overview
- [Overview](overview.md) — living synthesis

## Sources
- [Source Title](sources/slug.md) — one-line summary

## Entities
- [Entity Name](entities/EntityName.md) — one-line description

## Concepts
- [Concept Name](concepts/ConceptName.md) — one-line description

## Syntheses
- [Analysis Title](syntheses/slug.md) — what question it answers
```

---

## 6. Log Format（日志格式）

**适用文件：** `wiki/log.md`

**用途：** `wiki/log.md` 是 wiki 的追加式操作日志，记录每一次操作（ingest、query、health、lint、graph、report 等）。每次操作完成后在文件末尾追加一条新记录。

格式：

```
## [YYYY-MM-DD] <operation> | <title>
```

其中 `<operation>` 可以是：`ingest`、`query`、`health`、`lint`、`graph`、`report`