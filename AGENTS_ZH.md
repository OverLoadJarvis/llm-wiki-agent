# LLM Wiki Agent — 架构与工作流说明

本 Wiki 完全由您的代码代理维护。无需 API 密钥或 Python 脚本 — 只需在 Codex、OpenCode 或任何能读取此文件的代理中打开此仓库，直接与其对话即可。

## 使用方法

用简单的英语描述您想要做的事情：
- *"摄取此文件：raw/papers/my-paper.md"*
- *"Wiki 中关于 transformer 模型有什么内容？"*
- *"检查 Wiki 是否有孤立页面和矛盾内容"*
- *"构建知识图谱"*

或者使用快捷命令：
- `ingest <file>` → 运行摄取工作流
- `query: <question>` → 运行查询工作流
- `health` → 运行健康检查工作流（快速，每个会话运行一次）
- `lint` → 运行检查工作流（开销较大，定期运行）
- `build graph` → 运行图谱构建工作流

---

## 目录结构

```
raw/          # 不可变的源文档 — 切勿修改
wiki/         # 代理完全拥有此层
  index.md    # 所有页面的目录 — 每次摄取时更新
  log.md      # 追加式时间顺序记录
  overview.md # 所有源的动态综合
  sources/    # 每个源文档对应一个摘要页面
  entities/   # 人物、公司、项目、产品
  concepts/   # 想法、框架、方法、理论
  syntheses/  # 保存的查询答案
graph/        # 自动生成的图谱数据
tools/        # 独立的 Python 脚本
  health.py   # 结构检查（确定性，无 LLM 调用）
  lint.py     # 内容质量检查（使用 LLM 进行语义分析）
  build_graph.py  # 知识图谱生成
```

---

## 页面格式

每个 Wiki 页面使用以下 frontmatter：

```yaml
---
title: "页面标题"
type: source | entity | concept | synthesis
tags: []
sources: []       # 告知此页面的源文件别名列表
last_updated: YYYY-MM-DD
---
```

使用 `[[PageName]]` Wiki 链接链接到其他 Wiki 页面。

---

## 摄取工作流

触发方式：*"ingest <file>"*

**支持的格式：** Markdown (`.md`) 文件直接摄取。非 Markdown 文件（`.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.txt`, `.csv`, `.json`, `.xml`, `.rst`, `.rtf`, `.epub`, `.ipynb`, `.yaml`, `.yml`, `.tsv`, `.wav`, `.mp3`）在摄取前通过 [markitdown](https://github.com/microsoft/markitdown) 自动转换为 Markdown。使用 `--no-convert` 跳过自动转换。

步骤（按顺序）：
1. 完整读取源文档（非 Markdown 文件自动转换）
2. 读取 `wiki/index.md` 和 `wiki/overview.md` 获取当前 Wiki 上下文
3. 写入 `wiki/sources/<slug>.md` — 使用下方的源页面格式
4. 更新 `wiki/index.md` — 在 Sources 部分添加条目
5. 更新 `wiki/overview.md` — 如有必要修订综合内容
6. 更新/创建提及的关键人物、公司、项目的实体页面
7. 更新/创建讨论的关键想法和框架的概念页面
8. 标记与现有 Wiki 内容的任何矛盾
9. 追加到 `wiki/log.md`：`## [YYYY-MM-DD] ingest | <Title>`
10. **摄取后验证** — 检查断开的 `[[wikilinks]]`，验证所有新页面都在 `index.md` 中，打印更改摘要

### 源页面格式

```markdown
---
title: "源标题"
type: source
tags: []
date: YYYY-MM-DD
source_file: raw/...
---

## 摘要
2-4 句话的摘要。

## 关键主张
- 主张 1
- 主张 2

## 关键引用
> "引用内容" — 上下文

## 关联
- [[EntityName]] — 如何关联
- [[ConceptName]] — 如何连接

## 矛盾
- 与 [[OtherPage]] 在以下方面存在矛盾：...
```

### 特定领域模板

如果源属于特定领域（例如个人日记、会议记录），代理应使用专门的模板而非上面的默认通用模板：

#### 日记/日志模板
```markdown
---
title: "YYYY-MM-DD Diary"
type: source
tags: [diary]
date: YYYY-MM-DD
---
## 事件摘要
...
## 关键决策
...
## 精力与心情
...
## 关联
...
## 变化与矛盾
...
```

#### 会议记录模板
```markdown
---
title: "会议标题"
type: source
tags: [meeting]
date: YYYY-MM-DD
---
## 目标
...
## 关键讨论
...
## 做出的决策
...
## 行动项
...
```

---

## 查询工作流

触发方式：*"query: <question>"*

步骤：
1. 读取 `wiki/index.md` 识别相关页面
2. 读取这些页面
3. 使用内联引用（格式为 `[[PageName]]` Wiki 链接）综合答案
4. 询问用户是否要将答案保存为 `wiki/syntheses/<slug>.md`

---

## 检查工作流

触发方式：*"lint"*

检查内容：
- **孤立页面** — 没有其他页面指向的 `[[links]]` 的 Wiki 页面
- **断开的链接** — `[[WikiLinks]]` 指向不存在的页面
- **矛盾内容** — 跨页面冲突的主张
- **过时摘要** — 在新源之后未更新的页面
- **缺失实体页面** — 在 3 个以上页面中提及但没有自己页面的实体
- **稀疏页面** — 出站 `[[wikilinks]]` 少于 2 个的页面（链接密度预算）
- **数据缺口** — Wiki 无法回答的问题；建议新源

图谱感知检查（需要 `build graph` 生成的 `graph.json`）：
- **中心存根** — 上帝节点（度数 > μ+2σ）但内容薄弱（< 500 字符）
- **脆弱桥接** — 仅通过 1 条边连接的社区对
- **孤立社区** — 没有外部连接的集群

输出检查报告，并询问用户是否要保存到 `wiki/lint-report.md`。

---

## 健康检查工作流

触发方式：*"health"*

运行：`python tools/health.py`（或 `python tools/health.py --json` 获取机器可读输出）

快速结构完整性检查 — **零 LLM 调用**，每个会话运行安全：
- **空文件/存根文件** — 除 frontmatter 外无内容的页面（速率限制损害）
- **索引同步** — `wiki/index.md` 条目与磁盘上实际文件对比
- **日志覆盖** — 在 `wiki/log.md` 中缺少对应 `ingest` 条目的源页面

输出健康报告。使用 `--save` 保存到 `wiki/health-report.md`。

### 健康检查与内容检查的边界

| 维度 | `health` | `lint` |
|---|---|---|
| **范围** | 结构完整性 | 内容质量 |
| **LLM 调用** | 零 | 是（语义分析） |
| **成本** | 免费 | Token |
| **频率** | 每个会话，在其他工作之前 | 每 10-15 次摄取 |
| **检查项** | 空文件、索引同步、日志同步 | 孤立页面、断开链接、矛盾、缺口 |
| **工具** | `tools/health.py` | `tools/lint.py` |
| **运行顺序** | 首先（飞行前检查） | 健康检查通过后 |

> 先运行 `health` — 检查空文件会浪费 token。

---

## 图谱构建工作流

触发方式：*"build graph"*

首先尝试：`python tools/build_graph.py --open`

如果 Python/依赖不可用，手动构建：
1. 搜索所有 Wiki 页面中的 `[[wikilinks]]`
2. 构建节点（每页一个）和边（每链接一条）
3. 推断未被 Wiki 链接捕获的隐式关系 — 标记 `INFERRED` 并给出置信度分数；低置信度 → `AMBIGUOUS`
4. 写入 `graph/graph.json`，格式为 `{nodes, edges, built: date}`
5. 写入 `graph/graph.html` 作为自包含的 vis.js 可视化

---

## 命名约定

- 源文件别名：`kebab-case` 匹配源文件名
- 实体页面：`TitleCase.md`（例如 `OpenAI.md`, `SamAltman.md`）
- 概念页面：`TitleCase.md`（例如 `ReinforcementLearning.md`, `RAG.md`）

## 索引格式

```markdown
# Wiki 索引

## 概述
- [Overview](overview.md) — 动态综合

## 源
- [Source Title](sources/slug.md) — 单行摘要

## 实体
- [Entity Name](entities/EntityName.md) — 单行描述

## 概念
- [Concept Name](concepts/ConceptName.md) — 单行描述

## 综合
- [Analysis Title](syntheses/slug.md) — 回答的问题
```

## 日志格式

`## [YYYY-MM-DD] <operation> | <title>`

操作类型：`ingest`、`query`、`health`、`lint`、`graph`、`report`

---

## 图谱健康报告

触发方式：*"graph report"* 或 `python tools/build_graph.py --report`

`--report` 标志生成结构化的图谱健康报告，涵盖：
- **健康摘要** — 边/节点比率、孤立页面百分比、社区数量、链接密度
- **孤立节点** — 没有图谱连接的页面
- **上帝节点** — 度数 > μ+2σ 的中心页面（不成比例的连接性）
- **脆弱桥接** — 仅通过 1 条边连接的社区对
- **幽灵中心** — 被 2 个以上现有页面引用但指向不存在页面的 `[[wikilinks]]`（页面创建信号）

使用 `--save` 将报告写入 `graph/graph-report.md`。

---

## 第三阶段设计约束（自动链接 — 开放）

第三阶段提出基于图谱分析的自动 `[[wikilink]]` 插入。应用以下硬性规则：

### 升级门限：`draft → stable`
- 自动链接的边初始状态为 `DRAFT`（在图谱中可见，不写入页面正文）
- 专门的 `promote` 过程验证源基础 + 一致性
- 只有通过验证的边才能在页面中实现为 `[[wikilinks]]`
- **链接密度预算**：页面在升级前必须有 ≥2 个出站 Wiki 链接

### 硬性规则
| ID | 规则 | 原理 |
|---|---|---|
| HG-WA-01 | 图谱层不得从断开的链接自动创建页面 — 仅报告 | LLM 摄取会产生幻觉 Wiki 链接；自动创建会放大噪音 |
| HG-WA-02 | 新的斜杠命令不得重复现有命令的覆盖范围 | 防止用户混淆；改为合并到现有命令中 |