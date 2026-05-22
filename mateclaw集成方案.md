# MateClaw 多记忆与团队知识集成方案

**版本**：v2.2（第十三章：增补分阶段/按周逐步执行清单）  
**适用范围**：以 **MateClaw** 为 Agent 编排核心，经 **MCP** 接入团队工作区、中期反思、长期评分与审计、向量检索；**主推理、侧车与 Embedding 均以 MateClaw（及 Mem0 侧）已配置的模型与端点为准**，不强制使用 Ollama CLI。适用于私有化与强合规环境。  
**说明**：包名、CLI、环境变量与 JSON 均为**集成意图示例**；落地前须以各组件官方 README、锁定版本（commit / semver）及 **MCPHub** 实际 schema 逐项核对。模型**显示名**以控制台为准（如 `Qwen3.5-35B-A3B` 与厂商命名可能略有差异）。

---

## 文档导读（建议阅读顺序）

| 顺序 | 章节 | 内容 |
|:---:|:---|:---|
| 1 | [一、背景与目标](#一背景与目标) | 要解决什么问题、非目标 |
| 2 | [二、设计原则与三条上下文轴线](#二设计原则与三条上下文轴线) | 与 MateClaw 内置记忆如何分工 |
| 3 | [三、总体架构](#三总体架构) | 控制面 / 数据面、架构图 |
| 4 | [四、记忆分层与组件职责](#四记忆分层与组件职责) | 各层存储与接口语义 |
| 5 | [五、写入路径与读取路径](#五写入路径与读取路径) | 门控、分支、RAG、韧性 |
| 6 | [六、一致性与幂等](#六一致性与幂等) | SoT、Mem0、Replay、DLQ |
| 7 | [七、评分与冷启动](#七评分与冷启动) | 七因子、勿双叠加 |
| 8 | [八、主推理与模型分工](#八主推理与模型分工) | MateClaw 配置、三模型分工、预算、RAG 必做项 |
| 9 | [九、团队工作区与发布治理](#九团队工作区与发布治理) | MCP ROOT 同源、会诊 / PR |
| 10 | [十、组件清单与开源选型](#十组件清单与开源选型) | 部署形态、GitHub 推荐栈、MVP |
| 11 | [十一、集成拓扑与落地校验](#十一集成拓扑与落地校验) | 直连 / Hub / Sidecar、清单 |
| 12 | [十二、配置示例（概念）](#十二配置示例概念) | MCP 与 MateClaw / Mem0 模型配置 |
| 13 | [十三、部署节奏与执行计划](#十三部署节奏与执行计划) | 四周概览、阶段 0～5、**13.3 逐步清单**、**13.4 按周拆解** |
| 14 | [十四、指标、风险与可观测性](#十四指标风险与可观测性) | SLO、风险矩阵 |
| 附 | [附录 A · 术语表](#附录-a--术语表中英对照) | 术语 |
| 附 | [附录 B · 修订记录](#附录-b--文档修订记录) | 版本历史 |

---

## 一、背景与目标

### 1.1 要解决的问题

在团队场景下，将 MateClaw 扩展为**可运营的专业智能体平台**，同时具备：

- **团队级工作目录**：规范、模板、Runbook、工程产物等**共享证据**（非个人聊天流水账）。  
- **多领域知识**：跨会话、跨文档的**总结、抽取、检索**（RAG），且可审计。  
- **长期沉淀与门控**：低噪声写入、冲突处理、**权威源（SoT）** 与向量索引的最终一致。  
- **会诊 / 发布**：人类或流程对「晋升团队事实」把关（如 Git PR），再异步建索引。  
- **韧性**：MCP 多依赖下的超时、熔断、背压与降级。

### 1.2 非目标（避免范围膨胀）

- 不在本文档内规定 MateClaw **具体 Java 类名**与发版节奏（以应用仓库为准）。  
- 不将「图谱」列为首期必选项；算力紧张时 **dense 向量 + 可选 BM25** 优先。  
- 不假设所有组件均跑在 **同一块 GPU** 上与主推理模型分时共享（见第八章）。

### 1.3 成功判据（摘要）

| 维度 | 判据方向 |
|:---|:---|
| 效果 | 固定测试集上 Recall@K、空检索不误答；声明 **主推理模型**（如 Qwen3.5-35B-A3B）档位与量化 |
| 成本 | Token 注入预算可控；写路径异步，不拖垮主答 p95 |
| 合规 | 数据分级、全本地或混合路径书面勾选；敏感不入向量明文 |
| 运维 | trace_id 贯通；Git / Qdrant 可备份与 **Replay** |

---

## 二、设计原则与三条上下文轴线

### 2.1 控制平面与数据平面

- **控制平面**：MateClaw 决定调用哪些 MCP、并行度、降级策略；**MCPHub**（或等价网关）管理连接、健康检查、超时与熔断。  
- **数据平面**：各子系统读写各自介质（目录、PG、SQLite、Git、向量库）；**跨库强一致**不依赖单事务，依赖 **异步同步 + 重放 + SoT 定义**。

### 2.2 三条上下文轴线（须写入集成手册）

| 轴线 | 载体 | 用途 |
|:---|:---|:---|
| **A. Agent 内置 durable** | 数据库工作区（如 `PROFILE.md` / `MEMORY.md` / 日笔记）、结构化记忆、会话检索 | **该 Agent / 用户**的稳定偏好、叙事与工具可写状态 |
| **B. 团队工作区** | **MCP Filesystem**，`ROOT` 与 Workspace 绑定 | **团队共识**、目录级规范、会前会后材料、代码与导出 |
| **C. 团队语义索引** | **Mem0 + Qdrant**（可选 **RepoMemory** Git 为 SoT） | **跨文档语义召回**、元数据过滤、审计与重放 |

**硬规则**：轴线 **B、C** 的每条可检索对象须带 **`workspace_id`**，并推荐 **`domain`、`sensitivity`**；检索时先做 **元数据硬过滤**，再注入大模型。

### 2.3 Workspace 与 MCP ROOT 三处同源（强制）

1. 编排挂载到 MCP 容器/宿主机的 **volume 路径**；  
2. MCPHub `mcp_settings.json` 中 Filesystem 的 **`args` 最后一项 ROOT**；  
3. MateClaw 当前会话解析的 **workspace.base_path**（或等价）与审计日志字段。

三处不一致会导致「模型在错误目录上认真检索」。多团队时推介 **每 Workspace 独立 MCP 配置块** 或网关支持的动态路由。参考本仓库 `deploy/memory-infra/mcphub/README.md`。

---

## 三、总体架构

### 3.1 架构图

```mermaid
flowchart TB
    subgraph Control[控制平面]
        MC[MateClaw<br/>编排·策略·预算]
        GW[MCPHub<br/>路由·熔断·超时·限流]
    end

    subgraph Team[团队工作区]
        FS[Filesystem MCP<br/>共享目录证据]
    end

    subgraph Mid[中期]
        HD[Hindsight<br/>反思·心智模型]
    end

    subgraph Long1[长期·评分]
        OM[opencode-mem0<br/>多因子·冲突]
    end

    subgraph Long2[长期·SoT]
        RM[RepoMemory<br/>Git 审计]
    end

    subgraph Long3[长期·检索索引]
        M0[Mem0<br/>向量·可选图谱]
    end

    subgraph Infer[推理与压缩]
        COMP[LLMLingua<br/>可选]
        LLM[MateClaw已配置主模型<br/>如Qwen3.5-35B-A3B]
    end

    subgraph Data[数据面]
        PG[(PostgreSQL)]
        QD[(Qdrant)]
    end

    MC --> GW
    GW --> FS
    GW --> HD
    GW --> OM
    GW --> RM
    GW --> M0

    HD --> PG
    M0 --> QD

    OM -.->|高分| RM
    OM -.->|低分反思素材| HD
    RM -.->|异步索引| M0
    HD -.->|稳定实体可选| M0

    MC --> COMP
    COMP --> LLM
```

### 3.2 读图说明

- **实线**：运行期经 MCP 的主调用链。  
- **虚线**：MateClaw 或异步 Worker 触发的写入/索引，**非** MCP 图上的同步串行保证。  
- **Mem0**：相对 Git SoT 为**物化视图**；允许滞后，须支持 **Replay** 重建（见第六章）。

---

## 四、记忆分层与组件职责

| 层 | 英文概念 | 推荐组件 | 核心职责 | 典型工具语义 |
|:---|:---|:---|:---|:---|
| 团队工作区 | Team Workspace / Evidence | MCP Filesystem | 共享目录读、搜；与轴线 A 分工 | `read_file` / `search_files` |
| 中期 | Reflective / Episodic | Hindsight + PG | 反思、偏好、心智模型 | `recall` / `reflect`（以实际 MCP 为准） |
| 长期·评分 | Scoring & Arbitration | opencode-mem0 | 多因子打分、冷启动、冲突 | `score` / `merge`（示例） |
| 长期·SoT | Audit Log | RepoMemory | 不可变 Git 记录高分事实与元数据 | `commit` / `append`（示例） |
| 长期·检索 | Hybrid RAG Index | Mem0 + Qdrant | ANN、重排、可选 BM25 融合 | `search` / `add` |
| 上下文预算 | Compression | LLMLingua（可选） | 超预算压缩「检索块与历史摘要」 | 库调用，非 MCP |
| 主推理 | Reasoning | **MateClaw 已配置对话 API**（示例：`Qwen3.5-35B-A3B`） | 最终答复与复杂工具规划 | 与安装说明中「对话模型」一致 |

**RAG**：须同时定义 **Context Window（模型硬上限）** 与 **Injection Budget（编排注入上限）**，二者不是同一参数。

---

## 五、写入路径与读取路径

### 5.1 写入路径（回合 / 会话边界）

```
Turn 或 Session 结束
        │
        ▼
MateClaw Gate（去重·长度·敏感信息·业务标签）
        │
   ┌────┴────┐
   ▼         ▼
低价值      中高价值候选
（可不入长期链）   opencode-mem0：多因子评分 + 冲突检测
        ┌────────┴────────┐
        ▼                 ▼
   低于晋升阈值        高于晋升阈值
        ▼                 ▼
   Hindsight            RepoMemory（Git）
   （反思素材）         （SoT）
        │                 │
        └────────┬────────┘
                 ▼
        Mem0 索引流水线（异步）
        · Embedding → Qdrant
        · 失败入 DLQ 重试
```

### 5.2 读取路径（用户 Query）

```
Query
  │
  ▼
意图解析 + 可选查询改写（侧车如 **DeepSeek-V4-Flash**，避免主模型大批量 pairwise 打分）
  │
  ▼
MCPHub：并行 Fan-out（建议 ≤3 路）
  ├── Filesystem：团队目录证据
  ├── Hindsight：偏好 / 心智模型
  └── Mem0：向量（+ 可选 BM25 融合）
  │
  ▼
Fusion（RRF 或加权）→ 可选 Cross-Encoder 精排（CPU）
  │
  ▼
Top-K + MMR 去冗余
  │
  ▼
Prompt 组装（系统 > 安全 > 近期对话 > 检索块 > 工具摘要）
  │
  ▼
注入预算：未超则直送**主推理模型**；超则 LLMLingua（仅压检索块与历史摘要）
```

### 5.3 并发与韧性建议

| 参数 | 建议 | 说明 |
|:---|:---|:---|
| 检索 Fan-out | ≤3 | 与第八章 `retrieval_fan_out` 一致 |
| LLM 并发 | ≤2（按 GPU 调） | 避免 OOM |
| 单路 MCP 失败 | 降级为空集 | 主路径继续；须记录 trace |
| 队列 | 背压 | 写路径与索引异步，避免拖死读路径 |

---

## 六、一致性与幂等

| 概念 | 约定 |
|:---|:---|
| **SoT** | 团队「晋升事实」以 **Git（RepoMemory）+ 评分记录** 为准 |
| **Mem0 / Qdrant** | 检索优化副本；**最终一致**；须可从 Git **Replay** |
| **Hindsight** | 偏解释性状态；与向量库实体对齐规则须在集成层写明 |
| **幂等** | 同一 `memory_id` 或 `content_hash` 不重复产生无意义 Git 提交 |
| **DLQ** | Mem0 同步失败入队，可告警、可重试，禁止静默丢 |

---

## 七、评分与冷启动

### 7.1 七因子基线权重（归一化）

| 因子 | 英文 | 权重 | 含义摘要 |
|:---|:---|---:|:---|
| 重要性 | Salience / Utility | 20% | 信息增益 |
| 置信度 | Confidence | 15% | 用户显式确认等 |
| 新颖度 | Novelty | 15% | 相对已有知识 |
| 效用 | Task Utility | 15% | 对后续工具链 |
| 近因性 | Recency | 15% | 时间衰减 |
| 频率 | Frequency | 10% | 重复强度 |
| 干扰度 | Distraction / Conflict | 10% | 与库内冲突惩罚 |

### 7.2 冷启动与「勿双叠加」

冷启动窗口内可对权重做 **重归一化**（提升频率、近因等因子），或 **Gate 侧先验偏置**。**禁止** Gate 与评分引擎两侧同时强叠加同类偏置，易导致过冲。

工程上推介维护 **第二张冷启动权重表**，避免运行时解方程。

---

## 八、主推理与模型分工

**原则**：不强制 **Ollama**；**主对话、侧车路由、Embedding** 均以 **MateClaw 管理端 / 配置文件** 及 **Mem0 自身 `config.yaml`（或等价）** 中声明的模型名为准。下列三模型为**当前集成基线示例**（名称以实际网关返回为准）。

### 8.1 基线三模型（示例）

| 角色 | 示例模型 | 配置落点 | 职责 |
|:---|:---|:---|:---|
| **主推理** | `Qwen3.5-35B-A3B`（或控制台等价名） | MateClaw **默认对话模型** / Agent 绑定模型 | 最终答复、复杂工具规划、长上下文推理 |
| **侧车 / 快路径** | `DeepSeek-V4-Flash` | MateClaw **双 LLM / 路由**或独立「摘要用」端点（见安装说明） | 查询改写、会话摘要、门控后轻量打分、低成本批处理；**限流**，避免与主模型抢配额 |
| **向量嵌入** | `bge-large-zh-v15` | **Mem0** embedder 配置 +（若 MateClaw 单独展示 Embedding 模型）与之一致 | 中文团队知识 chunk 向量化；**写入与查询必须为同一模型、同一向量维度** |

**Mem0 侧**：须在 Mem0 环境或配置中指定与 **bge-large-zh-v15** 相同的 **Base URL、API Key、模型名**；Qdrant collection 的 **维度** 须与该 embedding 一致。

### 8.2 合规分叉（二选一或分环境）

| 模式 | 定义 | 推介场景 |
|:---|:---|:---|
| **A. 全私网** | 主推理、侧车、Embedding、重排均在**内网或签约 VPC** | 强数据出境限制 |
| **B. 混合** | 主推理仍在私网；Embedding / rerank / Flash 可走**合规云** | 无红线时提高 RAG 上限 |

须书面勾选；用配置开关禁用 B。

### 8.3 模型分工（核心）

| 职责 | 承担者 | 不推荐 |
|:---|:---|:---|
| 最终答复、复杂工具规划 | **Qwen3.5-35B-A3B**（MateClaw 主模型） | 用 Flash 顶替重推理主路径（除非已评估足够） |
| 评分辅助、摘要、轻量改写 | **DeepSeek-V4-Flash** 或规则 | **主模型大批量 pairwise 打分** |
| 精排 | **CPU Cross-Encoder** 或 bi-encoder | 主模型对每条候选做生成式相关判断 |
| Embedding | **bge-large-zh-v15**（与 Mem0 一致） | 与主 Chat 模型混用维度或混用不同 embed 模型写读 |

### 8.4 每回合预算（建议写入策略配置）

| 参数 | 初值方向 |
|:---|:---|
| `max_main_llm_calls` | 1～2 |
| `max_sidecar_llm_calls` | 0～2（Flash） |
| `retrieval_fan_out` | ≤3 |
| `injection_budget_tokens` | 2k～6k 自测 |
| `compress_after_tokens` | 超阈值再压；**只压检索块与历史摘要** |

### 8.5 RAG 必做项

1. **分块**：`chunk_size` / `overlap`；带 `source_id`、`updated_at`、`confidence`。  
2. **空检索**：拒答 / 追问 / 仅用会话内上下文，须**编排硬实现**。  
3. **输出约束**：先引用要点再结论或结构化 JSON。  
4. **读己写**：异步索引未就绪时，本会话高置信写入进 **scratch** 或与 Mem0 结果去重合并；或 `get_by_id` 同步读。

### 8.6 指标标定

Recall、压缩触发点、延迟目标须在 **实际选用的主推理模型与量化档位** 上标定，勿直接套用其他型号或 FP16 70B 的数值。详细测量方法见第十四章。

---

## 九、团队工作区与发布治理

| 能力 | 建议 |
|:---|:---|
| 长文档入库 | 异步 **Unstructured** 等解析，chunk 后再 embed |
| 结构化抽取 | 固定 **JSON Schema**（决议、行动项、Owner、Due、适用范围） |
| 会诊 / 发布 | **Git PR + CODEOWNERS** 或等价审批；合并后再触发索引 |
| 与 Hindsight / 内置摘要 | 写 **职责表**：团队事实走 Git→索引；反思状态走 Hindsight；避免同一语义三处双写 |

---

## 十、组件清单与开源选型

### 10.1 组件与部署

| 组件 | 协议/许可 | 典型部署 | 集成形态 |
|:---|:---|:---|:---|
| MateClaw | 依项目 | JAR / Compose | 编排宿主 |
| MCPHub | 依项目 | npm / 容器 | MCP 网关 |
| Filesystem MCP | Apache-2.0 | `npx @modelcontextprotocol/server-filesystem <ROOT>` | stdio |
| Hindsight | MIT | Docker / pip | stdio 或 HTTP |
| opencode-mem0 | MIT | 按官方（常为 OpenCode 插件）；本仓库 compose 未必含独立容器 | MCP / HTTP |
| RepoMemory | MIT | `npx … repomemory-http`（勿误写为 `repomemory serve`） | HTTP / MCP |
| Mem0 | Apache-2.0 | Python + 向量后端 | MCP / REST |
| Qdrant | 依版本 | 容器 / 托管 | 向量库 |
| LLMLingua | MIT | pip | 进程内库 |
| LLM 网关 | 依部署：DashScope / OpenAI 兼容 / 自建 | MateClaw **已配置** Base URL 与模型名 | 与安装说明一致 |

**环境预检**：Node ≥ 18；Python ≥ 3.10；Docker（若 PG/Qdrant 容器化）；磁盘与 Git 仓容量。

### 10.2 GitHub 推荐栈（按层）

> 落地锁定 **tag/commit**；大库重「持续维护」，小库可重「稳定少动」。

| 层 | 仓库 | 与主推理关系 |
|:---|:---|:---|
| 推理与嵌入 | **以 MateClaw / Mem0 配置为准**（可选：自建兼容 OpenAI 的网关） | 主模型少调用；**bge-large-zh-v15** 与 Mem0/Qdrant 维度锁死 |
| MCP | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 团队 ROOT；超时 |
| 网关 | [samanhappy/mcphub](https://github.com/samanhappy/mcphub) | 熔断、聚合 |
| 向量 | [qdrant/qdrant](https://github.com/qdrant/qdrant) | 与主推理并行 |
| 记忆 API | [mem0ai/mem0](https://github.com/mem0ai/mem0) | 关不必要的大模型写入链 |
| 精排（可选） | [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) | CPU / 小 GPU |
| BM25（可选） | [dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25) | RRF，无额外 LLM |
| 解析（可选） | [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) | 异步 Worker |
| 队列（可选） | [celery/celery](https://github.com/celery/celery) / [hatchet-dev/hatchet](https://github.com/hatchet-dev/hatchet) | 写路径与主推理错峰 |
| 观测（可选） | OpenTelemetry + Jaeger/Tempo；[langfuse/langfuse](https://github.com/langfuse/langfuse) | span 区分 embed / rerank / main |
| 压缩（可选） | [microsoft/LLMLingua](https://github.com/microsoft/LLMLingua) | 避免与主推理同卡争用 |
| Git 审计 | [rckflr/repomemory](https://github.com/rckflr/repomemory) | 异步 + PR 门禁 |

**MVP 建议**：MateClaw 模型端点已通 + MCPHub + Filesystem + Qdrant + Mem0（**bge-large-zh-v15** 写入/查询一致）+（可选）精排 + 基础日志/trace。

**可选附录**：若内网仍以 **Ollama** 提供与上述模型等价的本地推理，可单独维护「Ollama Modelfile / pull 列表」；本文档正文不依赖 Ollama CLI。

---

## 十一、集成拓扑与落地校验

### 11.1 拓扑

| 模式 | 描述 | 适用 |
|:---|:---|:---|
| A. 直连 MCP | MateClaw 直接 `mcpServers` | 开发 |
| B. MCPHub | 仅连 Hub | **生产推介** |
| C. Sidecar | 每类记忆独立容器 | 大规模隔离 |

### 11.2 落地清单（打勾）

1. `command` + `args` 在目标环境可启动；`npx` 缓存与 PATH 一致。  
2. Filesystem `ROOT` 沙箱化；**与 volume、workspace.base_path 同源**（第二章）。  
3. PG、Qdrant、Mem0 密钥 **env / 密钥管理**，不入库明文。  
4. 容器 memory、Git 体积、Qdrant 维度与距离度量（Cosine / Dot）有上限。  
5. **trace_id** 关联 MCP、评分、git_sha。  
6. `opencode-mem0` **npm bin** 以 README 为准；RepoMemory 使用 **`repomemory-http`**。

---

## 十二、配置示例（概念）

### 12.1 MCP 注册（示意）

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/var/mateclaw/workspace"]
    },
    "hindsight": {
      "command": "python",
      "args": ["-m", "hindsight"],
      "env": {
        "HINDSIGHT_DB_URL": "postgresql://user:pass@localhost:5432/mateclaw_hindsight"
      }
    },
    "opencode-mem0": {
      "command": "npx",
      "args": ["-y", "opencode-mem0", "serve"],
      "env": {
        "MEM0_DB_PATH": "/var/mateclaw/opencode-mem0.db"
      }
    },
    "repomemory": {
      "command": "npx",
      "args": [
        "--yes",
        "--package=@rckflr/repomemory@2.16.0",
        "repomemory-http",
        "--dir",
        "/var/mateclaw/repomemory-data",
        "--port",
        "8788"
      ]
    },
    "mem0": {
      "command": "python",
      "args": ["-m", "mem0.server"],
      "env": {
        "MEM0_VECTOR_STORE": "qdrant",
        "QDRANT_URL": "http://localhost:6333",
        "QDRANT_API_KEY": ""
      }
    }
  }
}
```

`MEM0_*`、`QDRANT_*` 须替换为所选 Mem0 发行版**实际**环境变量名。Hub 若支持 `timeoutMs`、`retry`，按 Hub 文档扩展。

### 12.2 MateClaw 与 Mem0 模型配置（基线示例）

**MateClaw（管理端 / `config`）**

- **默认对话模型**：`Qwen3.5-35B-A3B`（或与控制台一致的显示名）——主 Agent 答复与工具规划。  
- **侧车 / 双 LLM 路由**：`DeepSeek-V4-Flash`——摘要、改写、低成本步骤；与 [安装说明 → 双 LLM 检查表](./mateclaw安装目录与安装命令说明.md#mateclaw-dual-llm-checklist) 对齐。  
- 若 UI 单独配置 **Embedding 模型**：与 Mem0 使用的 **bge-large-zh-v15** 保持一致，便于运维对照（Mem0 仍以自身 embed 配置为写入真相源）。

**Mem0（`config.yaml` 或环境变量，以发行版为准）**

- **Embedder**：模型名 `bge-large-zh-v15`，**Base URL / API Key** 与生产网关一致；与 Qdrant collection **维度** 一致。  
- 若 Mem0 可选配置「摘要用 LLM」：推介指向 **DeepSeek-V4-Flash**，避免每条记忆都调用主推理模型。

**可选：Ollama 仅作自建网关时**

若内网通过 Ollama 暴露与上述同名模型，可保留内部 runbook（`ollama pull`、Modelfile `num_ctx` 等）；**集成验收仍以 MateClaw / Mem0 能成功调用模型 API 为准**，不强制团队安装 Ollama CLI。

**文档索引**

| 能力 | 文档 |
|:---|:---|
| 配置总览 | [安装说明 §1.2](./mateclaw安装目录与安装命令说明.md#mateclaw-config-overview) |
| Mem0 OSS | [安装说明 §8.3](./mateclaw安装目录与安装命令说明.md#mateclaw-mem0-config) |
| 双 LLM 检查表 | [安装说明 → 双 LLM](./mateclaw安装目录与安装命令说明.md#mateclaw-dual-llm-checklist) |

### 12.3 RepoMemory 留存（示意）

```json
{
  "retention": {
    "default_ttl": 31536000,
    "min_confidence": 0.7
  }
}
```

字段名以 RepoMemory 实际配置为准；TTL 为兜底，主策略仍靠评分与审计。

---

## 十三、部署节奏与执行计划

### 13.1 四周概览（与里程碑对齐）

| 周次 | 重点任务 | 验收 |
|:---|:---|:---|
| 第1周 | **MateClaw 与 Mem0 模型端点**（`Qwen3.5-35B-A3B` / `DeepSeek-V4-Flash` / `bge-large-zh-v15`）、MCPHub、PG、Qdrant、Filesystem（**ROOT 三处同源**） | Hub 全绿；三模型 smoke；样例 MCP 读成功 |
| 第2周 | opencode-mem0、RepoMemory、Mem0 写入；chunk **metadata** | Git 可追溯提交；向量可查 |
| 第3周 | Hindsight、Fusion、LLMLingua、降级；可选 CPU 精排 | 端到端引用检索块；**主推理 p95** 基线入库 |
| 第4周 | 压测、版本锁定、Replay、运维文档 | 发布 checklist；trace 可关联 |

### 13.2 分阶段里程碑（推荐顺序）

| 阶段 | 周期（参考） | 交付物 | 验收 |
|:---|:---|:---|:---|
| **0** 约束与基线 | 3～5 人日 | 合规 A/B 勾选；测试集与指标初值；`workspace_id` / `domain` / `sensitivity` 枚举 | 环境矩阵一页纸；**主模型-only** 压测留底 |
| **1** 基础设施 | 1～2 周 | Hub + Filesystem + PG + Qdrant + **三模型 API** 联调 + 基础 trace | ROOT 同源；超时熔断落库 |
| **2** 读路径 RAG | 1～2 周 | Mem0 读写；RRF/MMR；空检索硬策略 | Recall@5 与整轮 p95 记录 |
| **3** 写路径与 SoT | 1～2 周 | 评分、Git、异步索引、DLQ、读己写 | 候选→Git→异步可查；Replay 演练 |
| **4** 中期与运营 | 1～2 周（可与 3 并行） | Hindsight 职责表；LLMLingua GPU 争用监控；PR 发布 | 无三处互斥开放问题 |
| **5** 规模化 | 1 周+ | 压测、契约测试、值班手册 | 四周 checklist 全勾 |

**人周粗估**：1 全栈 + 1 运维约 **6～10** 周（含 MVP）；2～3 后端 + 运维约 **4～6** 周至阶段 3～4 试点。

### 13.3 分阶段逐步清单（子步骤与验收点）

下列编号为**推荐执行顺序**；同一编号内可并行。**验收**列全部打勾后，再进入下一阶段。

#### 阶段 0 — 约束与基线（约 3～5 人日）

| 步骤 | 动作 | 验收点 |
|:---:|:---|:---|
| 0.1 | 书面勾选数据路径：**第八章 8.2** 模式 A（全私网）或 B（混合）；法务/安全签字或等效工单 | 邮件/工单链接归档 |
| 0.2 | 定义 `workspace_id`、`domain`、`sensitivity` 枚举及**禁止写入向量**的敏感级别 | 枚举表入版本库或 Confluence |
| 0.3 | 建立 **dev / staging / prod**「环境矩阵」一页纸：MateClaw 版本、Hub 路径、Mem0 版本、Qdrant 端点、RepoMemory 端口 | 矩阵经评审签字 |
| 0.4 | 固化 **测试集**：≥N 条多轮对话 + 人工标注「应召回」的 memory_id 或 chunk_id；声明主模型为 **Qwen3.5-35B-A3B**（或实际名） | 测试集文件路径与版本号 |
| 0.5 | 指标初值写入表格（Recall@5、Token、p95、SLO），仅作基线不设死目标 | 第十四章表格填初值 |
| 0.6 | **主模型-only** 压测：MateClaw 直连主模型，单轮与多轮各若干次，记录 p50/p95、错误率 | 压测报告附件 |
| 0.7 | 确认 **Mem0** 与 **MateClaw** 调用 **bge-large-zh-v15** 的 Base URL / Key / 模型名字符串**完全一致**（避免双网关） | 两侧配置 diff 为零或已说明例外 |

#### 阶段 1 — 基础设施（约 1～2 周）

| 步骤 | 动作 | 验收点 |
|:---:|:---|:---|
| 1.1 | 部署 **PostgreSQL**（或复用现有实例）；创建 Hindsight / 业务表库（若分库则分别建） | `psql` 连通；备份策略写入 runbook |
| 1.2 | 部署 **Qdrant**；创建 collection：**维度 = bge-large-zh-v15 输出维度**；选定距离度量（Cosine / Dot） | 健康接口 200；维度文档化 |
| 1.3 | 部署 **MCPHub**；挂载 `mcp_settings.json` / `servers.json`（按 Hub 文档） | Hub UI 或日志显示已加载 Server |
| 1.4 | 配置 **Filesystem MCP**：`ROOT` = 团队目录；**宿主机 volume = Hub 容器内路径 = MateClaw `workspace.base_path`**（第二章 2.3） | 三处路径截图或脚本校验输出一致 |
| 1.5 | 自 Filesystem MCP 执行 `read_file`、`search_files` 各一次样例 | 返回内容与磁盘一致 |
| 1.6 | MateClaw 侧配置 **MCP 连接**（直连 Hub 或直连 Server）；填超时（如 15～30s）、重试策略 | 管理端「测试连接」成功或日志无 MCP 握手错误 |
| 1.7 | **三模型 smoke**：①主模型对话一条 ②Flash 走双 LLM/路由一条 ③Mem0 或独立脚本调用 **bge** 嵌入一条向量 | 三条请求均有 200/成功响应 |
| 1.8 | 最小 **trace_id**：MateClaw 日志或 OTel 中一次完整请求可 grep 到 `trace_id`；Hub 侧若支持则关联 | 样例 trace 导出 JSON 或截图 |
| 1.9 | Hub **熔断 / 超时**：故意停掉一个 MCP Server，确认主路径降级（第五章 5.3） | 降级日志 + 用户侧无白屏/无无限阻塞 |

#### 阶段 2 — 读路径 RAG（约 1～2 周）

| 步骤 | 动作 | 验收点 |
|:---:|:---|:---|
| 2.1 | 部署 **Mem0** 服务；`config` 指向 Qdrant；embedder = **bge-large-zh-v15** | Mem0 健康检查通过 |
| 2.2 | 实现 **chunk 管线**：解析（可选 Unstructured）→ 分块 `chunk_size`/`overlap` → 写入前校验 UTF-8 与最大长度 | 单文档端到端入库成功 |
| 2.3 | 每条向量写入 **payload/metadata**：至少 `workspace_id`、`source_id`、`updated_at`；推荐 `domain`、`sensitivity` | Qdrant UI 或 API 可查到字段 |
| 2.4 | 检索前 **硬过滤**：按 `workspace_id`（及 sensitivity）过滤后再 Top-K | 跨 workspace 零命中（负例测试） |
| 2.5 | **Fusion**：BM25（可选）+ 向量 **RRF** 或加权；参数写入配置 | 对比单路向量，Recall@5 有记录 |
| 2.6 | **MMR** 或等价去冗余；`Top-K` 默认 5 可配置 | 相邻重复 chunk 不出现在 Top-K |
| 2.7 | **空检索策略**在 MateClaw **编排代码或策略配置**中实现（第八章 **8.5 第 2 项**），非仅 prompt | 无命中时走拒答/追问/仅会话之一，可演示 |
| 2.8 | （可选）**CPU Cross-Encoder** 精排；对比无精排 p95 与 Recall | 对比表入报告 |
| 2.9 | 设定 **`injection_budget_tokens`**；超预算再走 LLMLingua（若启用） | 超长检索压测下不 OOM、不爆上下文 |

#### 阶段 3 — 写路径与 SoT（约 1～2 周）

| 步骤 | 动作 | 验收点 |
|:---:|:---|:---|
| 3.1 | 部署 **opencode-mem0**（或等价评分服务）；与 MateClaw **Gate** 职责划分文档化（第七章 7.2 勿双叠加） | 设计说明一页 |
| 3.2 | 接通「回合结束 → Gate → 评分」链路；低分/高分分支可配置阈值 | 日志可见分支命中统计 |
| 3.3 | 部署 **RepoMemory**（`repomemory-http`）；高分写入产生 **Git commit**；配置 `content_hash` / `memory_id` **幂等** | 重复提交不产生重复无意义 commit |
| 3.4 | 低分写入 **Hindsight**（或仅 PG），与 Git SoT 字段不冲突 | 样例低分条可查 |
| 3.5 | **异步流水线**：Git 合并后 → 队列任务 → Mem0 `add`/向量化；失败入 **DLQ** 可重试 | 故意杀 Mem0 一次，消息入 DLQ 并可重放成功 |
| 3.6 | **Replay 演练**：清空测试 collection → 自 Git 或导出日志重放 → Recall 恢复 | Runbook 步骤与截图 |
| 3.7 | **读己写**：本会话高置信写入进 scratch 或与检索结果去重合并（第八章 **8.5 第 4 项**） | 写入后立即追问，回答含新事实 |
| 3.8 | **PR 门禁**（第九章）：团队事实经 PR 合并后再触发「正式索引」任务（可与 3.5 同队列） | 一次完整 PR → 索引延迟可接受 |

#### 阶段 4 — 中期与运营（约 1～2 周，可与阶段 3 并行）

| 步骤 | 动作 | 验收点 |
|:---:|:---|:---|
| 4.1 | 部署 **Hindsight**（若阶段 2 未用）；与 MateClaw **内置摘要 / emergence** 写 **职责表** | 表内每条「谁写何种事实」有 Owner |
| 4.2 | 接通 Hindsight **recall** 至读路径 Fusion 一路（第五章） | Fusion 输出含 Hindsight 块 |
| 4.3 | **LLMLingua**（若用）：仅在超 `compress_after_tokens` 触发；监控与主推理 **GPU 争用** | Grafana/日志有压缩次数与耗时 |
| 4.4 | **CODEOWNERS** 与 PR 模板：必填 `workspace_id`、变更说明、回滚方式 | 示例 PR 通过评审 |
| 4.5 | 抽检 **评分偏差**：人工标注小样本 vs 评分排序，调权重表（第七章） | 抽检报告与参数变更记录 |

#### 阶段 5 — 规模化与发布（约 1 周+）

| 步骤 | 动作 | 验收点 |
|:---:|:---|:---|
| 5.1 | **压测**：并发用户或脚本；Hub、Qdrant、Git、MateClaw JVM 指标 | p95、错误率、资源峰值报告 |
| 5.2 | **版本锁定**：各组件 semver 或 commit；`npm ci` / 镜像 digest 固化 | lockfile 或 BOM 入仓库 |
| 5.3 | **契约测试**：对关键 MCP tool 做 schema 快照测试（CI） | CI 绿 |
| 5.4 | **运维手册**：RPO/RTO、备份还原、Replay、值班、告警路由、密钥轮换 | On-call 签字 |
| 5.5 | **发布 checklist**（含第十三章全部验收摘要） | 发布会议记录 |

### 13.4 按周拆解（与 13.1 对照；可映射到人天）

> 以下为「最小团队」建议排期；人力增加时可合并周次。**D** = 自然日序号（可按周一起算）。

#### 第 1 周（对齐阶段 0 末 + 阶段 1）

| D | 聚焦 | 对应子步骤 |
|:---:|:---|:---|
| D1～D2 | 环境矩阵、合规勾选、枚举与测试集 | 0.1～0.5 |
| D3 | 主模型压测 + bge 配置对齐 | 0.6～0.7 |
| D4 | PG + Qdrant 部署与校验 | 1.1～1.2 |
| D5 | MCPHub + Filesystem + ROOT 三处同源校验 | 1.3～1.5 |
| D6～D7 | MateClaw 接 Hub、三模型 smoke、trace、熔断演练 | 1.6～1.9 |

**周末验收**：Hub 全绿；三模型 smoke 通过；ROOT 同源有证据。

#### 第 2 周（对齐阶段 2 前半 + 阶段 3 准备）

| D | 聚焦 | 对应子步骤 |
|:---:|:---|:---|
| D8～D9 | Mem0 部署、chunk 管线、metadata | 2.1～2.3 |
| D10～D11 | 硬过滤、Fusion、MMR、空检索硬策略 | 2.4～2.7 |
| D12 | 可选精排、注入预算与压缩试验 | 2.8～2.9 |
| D13～D14 | opencode-mem0 与 Gate 文档、RepoMemory 起服务 | 3.1～3.3 |

**周末验收**：Mem0 检索闭环；至少一条 Git commit 来自评分晋升试验（或预发环境）。

#### 第 3 周（对齐阶段 3 末 + 阶段 4）

| D | 聚焦 | 对应子步骤 |
|:---:|:---|:---|
| D15～D16 | 异步索引、DLQ、Replay、读己写 | 3.4～3.7 |
| D17 | PR 门禁与索引联动 | 3.8 |
| D18～D19 | Hindsight 与职责表、接入 Fusion | 4.1～4.2 |
| D20～D21 | LLMLingua 与 GPU 监控、抽检流程 | 4.3～4.5 |

**周末验收**：端到端问答可引用检索块；主推理 p95 基线入库；读己写演示通过。

#### 第 4 周（对齐阶段 5）

| D | 聚焦 | 对应子步骤 |
|:---:|:---|:---|
| D22～D23 | 压测与调参 | 5.1 |
| D24～D25 | 版本锁定与契约测试 | 5.2～5.3 |
| D26～D28 | 运维手册、发布 checklist、评审上线 | 5.4～5.5 |

**周末验收**：发布 checklist 全勾；staging 与 prod 变更单关闭。

---

### 14.1 指标（示例目标，须用自有测试集标定）

| 指标 | 英文 | 目标示例 | 测量要点 |
|:---|:---|:---|:---|
| 跨会话召回 | Recall@K | 如 ≥82% | 人工标注 memory_id；Recall@5 |
| Token 成本 | Token Savings | 如 ≥70% | 全量上下文 vs 检索+压缩 |
| 压缩保真 | Compression Fidelity | 如 ≥92% | ROUGE/BERTScore 或任务通过率 |
| 延迟 | p95 Latency | 视硬件 | 区分冷启动与热路径；声明 **Qwen3.5-35B-A3B**（或实际主模型） |
| 可用性 | SLO | 如 ≥99.5% | MCP 成功率月度窗口 |

### 14.2 风险矩阵

| 风险 | 严重度 | 应对 |
|:---|:---|:---|
| GPU OOM | 高 | 限 `num_ctx`、并发；侧车 **Flash** 与主推理分卡/分时 |
| PG 丢失 | 高 | WAL、备份、RPO/RTO |
| Qdrant 损坏 | 中 | 快照；Git Replay |
| Git 膨胀 | 中 | `git gc`、LFS / 外置 blob |
| MCP 契约变更 | 中 | 锁版本；契约测试 |
| 评分偏差 | 中 | 抽检与权重表迭代 |
| Hub 单点 | 低 | 多实例、健康路由、客户端超时 |

**可观测性**：OpenTelemetry 或结构化日志；字段至少含 `trace_id`、`session_id`、`memory_id`、`git_sha`、`workspace_id`。

---

## 附录 A · 术语表（中英对照）

| 中文 | English | 简释 |
|:---|:---|:---|
| 模型上下文协议 | MCP | 工具与数据源标准协议 |
| 检索增强生成 | RAG | 检索结果注入后再生成 |
| 权威源 | SoT | 争议时以该存储为准 |
| 物化视图 | Materialized View | Mem0 相对 Git 的派生检索副本 |
| 重放 | Replay | 按 Git/日志重建向量索引 |
| 门控 | Gating | 写入评分前的过滤 |
| 冷启动 | Cold Start | 缺先验时的权重或先验补偿 |
| 元数据硬过滤 | Metadata Hard Filter | 检索前按 workspace 等过滤 |
| 读己写 | Read-Your-Writes | 异步索引未就绪时的会话内补偿 |
| 熔断 / 背压 / 优雅降级 | Circuit Breaking / Backpressure / Graceful Degradation | 韧性模式 |
| 互易排名融合 | RRF | 多路检索结果融合 |
| 最大边际相关性 | MMR | 结果多样性截断 |

---

## 附录 B · 文档修订记录

| 版本 | 变更摘要 |
|:---|:---|
| **v2.2** | 第十三章增补 **13.3 分阶段逐步清单**（0.1～5.5 子步骤+验收）、**13.4 按周拆解**（D1～D28）；文首 v2.2 |
| **v2.1** | 模型栈改为 **MateClaw 已配置 API**：基线示例 **Qwen3.5-35B-A3B**、**DeepSeek-V4-Flash**、**bge-large-zh-v15**；架构图与第八章重写；去除正文对 Ollama CLI 的依赖（保留可选自建说明）；第十三章 W1 / 阶段 0 / 指标与风险用语同步 |
| **v2.0** | **全文重构**：导读表；合并原「四层 / 团队轴线 / 32B / 开源 / 执行计划」为单线章节；统一编号；删除重复小节与交叉引用混乱 |
| v1.3～v1.0 | 历史增量内容已吸收进 v2.0；细粒度变更不再逐条展开 |

---

**维护提示**：将贵司 **MateClaw 版本号**、**MCPHub 配置文件路径**、**Mem0 发行版** 填入内部「环境矩阵」表（dev/staging/prod），与本方案一并评审存档。
