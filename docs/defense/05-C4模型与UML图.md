# C4 模型与 UML 图集

> 版本: 1.0
> 日期: 2026-05-13
> 用途: 15 分钟架构设计专题讲解的图示材料
> 原则: 所有图基于实际实现，不包含不存在的服务或组件

---

## 图 1: C4 Context 图（系统上下文）

### Mermaid 代码

```mermaid
graph TB
    User["👤 用户<br/>课程学生 / 开发者"]
    Browser["🌐 Web 浏览器<br/>Mermaid.js + marked.js"]
    System["🏛 架构风格智能助手<br/>Architecture Assistant<br/>6 微服务 + 前端 + Neo4j"]
    LLM["🤖 LLM 服务<br/>DeepSeek v4-Flash<br/>OpenAI 兼容协议"]
    Neo4j["🗄 Neo4j 5.26<br/>图数据库 (可选)"]

    User -->|"输入需求文本"| Browser
    Browser -->|"POST /api/v1/recommend"| System
    System -->|"推荐报告 + 对比矩阵 + ADR"| Browser
    Browser -->|"渲染 11 个展示区块"| User
    System -->|"POST /chat/completions<br/>语义补全 / 投票 / 摘要"| LLM
    LLM -->|"JSON / 文本 响应"| System
    System -->|"Cypher 查询<br/>HAS_QUALITY / COMPLEMENTS"| Neo4j
    Neo4j -->|"匹配属性 / 场景 / 风险"| System

    style LLM fill:#ffe6e6,stroke:#cc0000,stroke-dasharray: 5 5
    style Neo4j fill:#e6e6ff,stroke:#0000cc,stroke-dasharray: 5 5
```

> 图例: 红色虚线 = 外部 LLM 服务（系统边界外，可选）；蓝色虚线 = Neo4j 图数据库（可选后端）

### 在答辩中什么时候讲

**时间段**: 1:30-3:30（C4 Context 部分，约在第 3 页 PPT）

在讲完"项目背景与问题定义"之后，引出第一张架构图。用这张图建立观众对系统整体边界的认知。

### 讲图的 1 分钟话术

> 我们用 C4 模型来表达架构。首先是 **C4-Context，系统上下文图**——它回答"我们的系统在世界上和谁交互"。
>
> 中间是我们的系统——架构风格智能助手，由 6 个后端微服务、1 个前端和 1 个 Neo4j 图数据库组成。
>
> 系统有三个外部交互对象——
>
> 左边是**用户**，通过浏览器输入自然语言需求，看到推荐报告。
>
> 右下是**外部 LLM 服务**。注意它用红色虚线标注——它**在系统边界之外**。这意味着 LLM 不是一个必需组件。它不可用时系统自动降级为纯规则模式，核心推荐链路不受影响。
>
> 右边是 **Neo4j 图数据库**，用蓝色虚线标注——它也是**可选后端**。系统同时内置了 JSON 文件后端，Neo4j 不可用时自动切换。
>
> 这张图的核心信息是：**两个虚线框都不是系统生存的必需品。** 去掉 LLM 和 Neo4j，系统仍然可以完整运行。

### 老师可能追问

**Q: 为什么把 LLM 画在系统边界外？**

> 这是有意为之的设计表达。LLM 在系统边界外意味着三件事：一是它的可用性波动不影响核心链路；二是改环境变量就能换模型——DeepSeek、通义千问、GPT-4 任意切换；三是系统启动时检测 LLM 是否配置，未配置就跳过所有 LLM 调用。回归测试验证了纯规则模式 20/20 全通过。

**Q: Neo4j 也是虚线，它和 JSON 后端是什么关系？**

> 双后端架构——地位平等，不是"主从"。`KNOWLEDGE_BACKEND` 环境变量控制：json 模式零外部依赖，neo4j 模式使用图数据库，auto 模式自动探测——Neo4j 可用就用，不可用就回退 JSON。虚线不是"不重要"，是"可选"。

---

## 图 2: C4 Container 图（容器级）

### Mermaid 代码

```mermaid
graph TB
    subgraph UserDevice["用户终端"]
        Browser["🌐 Web 浏览器<br/>Mermaid.js + marked.js"]
    end

    subgraph SystemBoundary["架构风格智能助手 — Docker Compose"]
        subgraph FrontendLayer["前端层"]
            Frontend["frontend<br/>Nginx :3000→80<br/>index.html 289行"]
        end

        subgraph GatewayLayer["网关层"]
            Gateway["api-gateway :8000<br/>FastAPI 226行<br/>双引擎编排 + 缓存"]
        end

        subgraph AgentLayer["Agent 层 — 4 个业务微服务"]
            ReqAgent["requirements-agent<br/>:8001 — 272行<br/>规则提取 + LLM 补全"]
            MatchAgent["matching-agent<br/>:8002 — 378行<br/>规则评分 + 图谱 + 组合"]
            EvalAgent["evaluation-agent<br/>:8003 — 393行<br/>LLM 投票 + 摘要 + ADR"]
            RefAgent["refactoring-agent<br/>:8005 — 340行<br/>坏味检测 + 迁移建议"]
        end

        subgraph DataLayer["数据层"]
            KB["knowledge-base :8004<br/>双后端调度<br/>JSON 234行 + Neo4j 388行"]
            Neo4jDB["Neo4j 5.26<br/>:7474 :7687<br/>可选图数据库"]
            JSONFiles["JSON 文件存储<br/>10风格 + 5组合<br/>反馈 + 权重 + ADR"]
        end
    end

    subgraph ExternalServices["外部服务"]
        LLM["🤖 DeepSeek API<br/>可选 LLM 服务"]
    end

    Browser -->|"POST /api/v1/recommend"| Frontend
    Frontend -->|"代理转发"| Gateway
    Gateway -->|"POST /extract"| ReqAgent
    Gateway -->|"POST /match"| MatchAgent
    Gateway -->|"POST /evaluate"| EvalAgent
    Gateway -->|"POST /refactor (非阻塞)"| RefAgent
    MatchAgent -->|"GET /styles /weights /combinations"| KB
    MatchAgent -->|"POST /graph/match"| KB
    EvalAgent -->|"POST /adr"| KB
    KB -->|"Cypher"| Neo4jDB
    KB -->|"读写"| JSONFiles
    ReqAgent -.->|"语义补全 (15s)"| LLM
    EvalAgent -.->|"投票 (20s) + 摘要 (25s)"| LLM
    RefAgent -.->|"可选润色 (15s)"| LLM

    style LLM fill:#ffe6e6,stroke:#cc0000,stroke-dasharray: 5 5
    style Neo4jDB fill:#e6e6ff,stroke:#0000cc,stroke-dasharray: 5 5
    style FrontendLayer fill:#f0fff0,stroke:#008800
    style GatewayLayer fill:#fff8e0,stroke:#cc8800
    style AgentLayer fill:#f0f8ff,stroke:#0066cc
    style DataLayer fill:#fff0f0,stroke:#cc0066
```

> 图例: 红色虚线 = 外部可选 LLM；蓝色虚线 = 内部可选 Neo4j。四层背景色分别标注前端层/网关层/Agent层/数据层。

### 在答辩中什么时候讲

**时间段**: 3:30-5:30（C4 Container 部分，约在第 4-5 页 PPT）

紧跟 C4 Context 之后，把系统内部展开为容器级视图。先花 30 秒让观众看清四层结构，再逐层讲解。

### 讲图的 1 分钟话术

> 接下来把系统拆开，看 **C4-Container 图**。这里的"容器"是指可独立部署的运行单元。
>
> 系统分为四层——
>
> 最上层**前端层**：nginx 托管一个 289 行的 HTML 页面，不依赖任何前端框架，通过 CDN 加载 Mermaid.js 和 marked.js。
>
> 往下**网关层**：api-gateway，系统的唯一对外入口。负责 Pydantic 校验、缓存检查、双引擎编排。如果 LangGraph 没安装，自动回退手动编排。
>
> 中间是 **Agent 层**——4 个业务微服务。requirements-agent 做特征提取，规则引擎主导；matching-agent 做架构匹配，规则评分 + 图谱融合 + 组合推荐；evaluation-agent 做最终评估，LLM 投票 + 摘要 + ADR 生成；refactoring-agent 做重构建议，非阻塞异步调用。
>
> 最下层**数据层**——knowledge-base 通过统一的调度函数在 JSON 和 Neo4j 之间切换，调用方不感知。
>
> 注意三个虚线箭头指向 LLM——表示三处 LLM 调用都是可选的、可超时的、可降级的。

### 老师可能追问

**Q: 为什么 evaluation-agent 是最大的（393 行）？它是不是承担了太多职责？**

> evaluation-agent 确实是最复杂的 Agent——它并行调用 LLM 做投票和摘要、构建 6 列对比矩阵、生成动态风险评估、写入 ADR、嵌入组合推荐。但它的所有职责都围绕一个目标——"把候选列表变成最终推荐报告"。如果进一步拆分，可以把 ADR 生成独立出来，当前是考虑到拆分的边际收益不如先把代码写清楚。393 行在单个 FastAPI 文件中还在可管理的范围内。

---

## 图 3: UML 时序图（完整推荐流程）

### Mermaid 代码

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as Frontend<br/>Nginx :3000
    participant G as API Gateway<br/>:8000
    participant R as Requirements<br/>Agent :8001
    participant M as Matching<br/>Agent :8002
    participant E as Evaluation<br/>Agent :8003
    participant Ref as Refactoring<br/>Agent :8005
    participant K as Knowledge<br/>Base :8004
    participant L as LLM<br/>DeepSeek

    U->>F: 输入需求文本，点击"开始推荐"
    F->>G: POST /api/v1/recommend
    G->>G: Pydantic 校验 (min_length=10)
    G->>G: 缓存检查

    rect rgb(240,245,255)
        Note over G,R: 阶段1: 特征提取 (~200ms)
        G->>R: POST /extract
        R->>R: 关键词匹配 10维词典
        R->>R: 否定语义过滤
        alt 规则命中 ≤2 且 LLM 已配置
            R->>L: Few-shot 语义补全 (15s超时)
            L-->>R: JSON 特征补全
        end
        R-->>G: features + feature_hits
    end

    rect rgb(255,248,240)
        Note over G,M: 阶段2: 架构匹配 (~500ms)
        G->>M: POST /match
        M->>K: GET /styles + /weights + /combinations
        K-->>M: 10风格 + 权重 + 5组合
        M->>M: score_style() 规则评分
        M->>K: POST /graph/match
        alt Neo4j 可用
            K-->>M: 图谱证据 (属性/场景/风险)
            M->>M: blend_scores() 融合 (上限50%)
        else Neo4j 不可用
            K-->>M: available: false
        end
        M->>M: 组合评分排序
        M-->>G: candidates + combination_candidates
    end

    rect rgb(240,255,240)
        Note over G,E: 阶段3: 评估决策 (~3-8s)
        G->>E: POST /evaluate
        par LLM 并行调用
            E->>L: 风格投票 (20s超时, t=0.0)
            L-->>E: 最佳风格名
        and
            E->>L: 摘要生成 (25s超时, t=0.3)
            L-->>E: Few-shot 结构化摘要
        end
        alt LLM 投票或摘要失败
            E->>E: _fallback_summary() 模板
        end
        E->>E: 混合推理 + 构建对比矩阵
        E->>E: 动态风险评估
        E->>K: POST /adr (非阻塞)
        K-->>E: adr_id / adr_status
        E-->>G: final_report (含 ADR)
    end

    rect rgb(255,240,255)
        Note over G,Ref: 阶段4: 重构建议 (非阻塞)
        G->>Ref: POST /refactor (8s超时)
        alt 输入含重构信号
            Ref->>Ref: 坏味检测 + 模式选择
            Ref->>L: 可选 LLM 润色 (15s超时)
            Ref-->>G: refactoring_advice
        else 无重构信号
            Ref-->>G: refactoring_needed: false
        else 超时或失败
            Ref-->>G: refactoring_advice: {}
        end
    end

    G->>G: 写入缓存
    G-->>F: RecommendResponse (含所有字段)
    F->>F: 渲染 11 个展示区块
    F-->>U: 完整推荐报告
```

### 在答辩中什么时候讲

**时间段**: 5:30-7:30（Agent 协作机制部分，约在第 6 页 PPT）

用这张图展示一次完整请求经过的所有阶段，让观众理解 4 个 Agent 如何协作、LLM 在哪里参与、降级在哪里发生。建议边讲边用手指追踪时序线。

### 讲图的 1 分钟话术

> 这张 UML 时序图展示了一次完整推荐请求的全过程。从上到下，时间是竖轴。
>
> 用户在前端输入文本，请求到达 API Gateway。Gateway 先做校验和缓存检查。
>
> **蓝色区域——阶段 1：特征提取。** Gateway 调用 requirements-agent。Agent 跑关键词匹配和否定过滤，如果关键词命中太少且 LLM 已配置，触发 LLM 语义补全——这个调用有 15 秒超时，失败则静默跳过。
>
> **橙色区域——阶段 2：架构匹配。** matching-agent 从 knowledge-base 拉取 10 种风格和权重数据，跑规则评分。然后尝试获取 Neo4j 图谱证据——可用就通过 blend_scores 融合，不可用就跳过。
>
> **绿色区域——阶段 3：评估决策。** 这是最关键的阶段。evaluation-agent 并行调用 LLM 做两件事——投票选最佳风格、生成中文摘要。两个调用同时发出，减少串行等待。LLM 失败则用规则模板。
>
> **紫色区域——阶段 4：重构建议。** Gateway 异步调用 refactoring-agent，8 秒超时，失败了不阻塞主流程。
>
> 整个过程四个阶段顺序执行，但阶段 3 内部的 LLM 调用是并行的。最后 Gateway 写缓存，前端渲染 11 个展示区块。

### 老师可能追问

**Q: 为什么阶段 3 的 LLM 调用用并行而不用串行？**

> 投票和摘要这两个 LLM 调用互不依赖——投票只需要候选列表，摘要只需要候选列表加需求文本。并行执行通过 `asyncio.gather` 实现，在 Python FastAPI 的 async 环境下，网络 I/O 不会被阻塞。两个调用串行需要约 8-12 秒，并行可以降到约 4-6 秒。但如果 LLM API 有并发限制（比如同一 API Key 不能同时发两个请求），这个设计需要调整——这是一个已知的适配考虑。

**Q: ADR 写入失败了怎么办？**

> ADR 写入是 `try/except` 包装的非阻塞调用。写入失败会在 `final_report.adr` 中设置 `adr_status: "failed"`，但推荐主流程继续返回。前端 ADR 区块会显示"未生成 ADR"。ADR 是重要的溯源手段，但不应该是推荐链路的阻塞点。

---

## 图 4: Agent 协作图

### Mermaid 代码

```mermaid
graph TB
    subgraph Orchestrator["编排层 — API Gateway :8000"]
        direction LR
        LangGraph["LangGraph StateGraph<br/>4节点顺序执行"]
        Manual["手动编排<br/>httpx 顺序调用"]
        LangGraph -.->|"不可用时回退"| Manual
    end

    subgraph AgentCluster["Agent 层 — 4 个业务微服务"]
        Req["Requirements Agent<br/>:8001<br/>━━━━━━━━━━<br/>输入: 需求文本<br/>输出: 10维特征 + 关键词<br/>━━━━━━━━━━<br/>核心方法:<br/>keyword_hits() 关键词匹配<br/>filter_negation() 否定过滤<br/>llm_semantic_supplement() LLM补全"]

        Match["Matching Agent<br/>:8002<br/>━━━━━━━━━━<br/>输入: 特征布尔映射<br/>输出: Top3候选 + 组合候选<br/>━━━━━━━━━━<br/>核心方法:<br/>score_style() 规则评分<br/>blend_scores() 图谱融合<br/>rank_combinations() 组合排序"]

        Eval["Evaluation Agent<br/>:8003<br/>━━━━━━━━━━<br/>输入: 需求 + 特征 + 候选<br/>输出: 最终推荐报告<br/>━━━━━━━━━━<br/>核心方法:<br/>llm_vote_style() 投票<br/>llm_summary() 摘要<br/>_fallback_summary() 模板"]

        Ref["Refactoring Agent<br/>:8005<br/>━━━━━━━━━━<br/>输入: 需求 + 推荐风格<br/>输出: 重构建议<br/>━━━━━━━━━━<br/>核心方法:<br/>detect_smells() 坏味检测<br/>select_patterns() 模式选择<br/>llm_polish() 可选润色"]
    end

    subgraph DataLayer["数据层"]
        KB["Knowledge Base :8004<br/>JSON + Neo4j 双后端<br/>10风格 + 5组合 + ADR"]
    end

    Orchestrator -->|"1. POST /extract"| Req
    Orchestrator -->|"2. POST /match"| Match
    Orchestrator -->|"3. POST /evaluate"| Eval
    Orchestrator -->|"4. POST /refactor (非阻塞)"| Ref
    Match -->|"GET /styles /weights"| KB
    Match -->|"POST /graph/match"| KB
    Eval -->|"POST /adr"| KB

    style Orchestrator fill:#fff8e0,stroke:#cc8800
    style AgentCluster fill:#f0f8ff,stroke:#0066cc
    style DataLayer fill:#fff0f0,stroke:#cc0066
    style Ref fill:#f5f0ff,stroke:#8800cc
```

> 说明: Refactoring Agent 用紫色标注——它是非阻塞异步调用，失败不影响主推荐流程。

### 在答辩中什么时候讲

**时间段**: 5:30-7:30（Agent 协作机制部分，约在第 7 页 PPT）

在 UML 时序图之后，用这张图总结 4 个 Agent 各自的输入输出和核心方法。帮助观众从"流程视角"切换到"组件视角"。

### 讲图的 1 分钟话术

> 这张图从组件视角看 4 个 Agent 的职责边界——
>
> **Requirements Agent**：输入是自然语言文本，输出是 10 维特征布尔映射和命中关键词列表。核心方法是关键词匹配、否定过滤、LLM 语义补全。LLM 补全只在特征稀疏时触发。
>
> **Matching Agent**：输入是特征映射，输出是 Top 3 候选和组合候选。核心方法是规则评分、图谱融合、组合排序。它从 knowledge-base 拉取风格数据和权重，并行获取图谱证据。
>
> **Evaluation Agent**：输入是需求文本、特征和候选列表，输出是最终推荐报告。核心方法是 LLM 投票、LLM 摘要和规则 fallback。它是唯一直接调用 LLM 做决策评估的 Agent。
>
> **Refactoring Agent**：输入是需求文本和推荐风格，输出是重构建议。紫色标注表示它是非阻塞调用——Gateway 调用它时不等待，失败了上面三个 Agent 的结果不受影响。
>
> 四个 Agent 之间不直接通信——都通过 Gateway 编排和 knowledge-base 数据层交互。这是 Pipeline-Agent 模式的典型特征。

### 老师可能追问

**Q: 为什么 Agent 之间不直接通信？**

> 这是有意的设计选择。Agent 之间直接通信会增加耦合——比如 matching-agent 直接调 evaluation-agent，那一旦 evaluation-agent 的接口变化，matching-agent 也要改。通过 Gateway 集中编排，Agent 只需要知道自己的输入输出格式，不需要知道其他 Agent 的存在。这个模式叫"编排式协作"（Orchestration），而不是"舞蹈式协作"（Choreography）。

---

## 图 5: 混合推理流程图

### Mermaid 代码

```mermaid
graph TB
    Input["📝 自然语言需求文本<br/>'开发跨平台即时通讯系统...'"]

    subgraph L1["Layer 1: 规则引擎 — 确定性基线 (始终运行)"]
        KW["10维关键词词典匹配<br/>~100个中英文关键词"]
        Neg["否定语义过滤<br/>6个否定词窗口检测"]
        Feat["10维特征布尔映射<br/>+ 命中关键词证据"]
        KW --> Neg --> Feat
        LLM_Supp["LLM 语义补全 (条件触发)<br/>命中维度 ≤2 且 LLM 已配置<br/>temperature=0.1, timeout=15s"]
        Feat -.->|"稀疏时触发"| LLM_Supp
        LLM_Supp -.->|"失败静默跳过"| Feat
    end

    Input --> KW

    subgraph L2["Layer 2: 知识图谱 — 关系推理增强 (Neo4j 可用时运行)"]
        Cypher["Cypher 图查询<br/>HAS_QUALITY 关系遍历<br/>每个匹配属性 +2分"]
        Scene["查询 SUITABLE_FOR 场景<br/>查询 HAS_RISK 风险<br/>查询 COMPLEMENTS 互补"]
        GraphScore["图谱得分 = min(graph_bonus, rule_score//2)<br/>上限 50%，防止图谱主导"]
        Cypher --> Scene --> GraphScore
    end

    Feat --> Cypher
    Feat --> Score

    subgraph L3["Layer 3: 规则评分引擎 (始终运行)"]
        Score["score_style() 计算<br/>标签匹配+2 + 学习权重+1 + 特定规则+1"]
        Learn["学习权重加成<br/>(≥2次确认的特征-风格关联)"]
        Mainstream["主流保底策略<br/>Layered/Microservices/Event-Driven 必现"]
        Score --> Learn
        Score --> Mainstream
    end

    Blend["blend_scores() 融合<br/>最终分 = 规则分 + 图谱加分"]
    Score --> Blend
    GraphScore --> Blend

    Top3["Top 3 候选架构<br/>含分数 / 理由 / 图谱证据"]

    Blend --> Top3

    subgraph L4["Layer 4: LLM 评估层 — 语义理解 (LLM 可用时运行)"]
        Vote["LLM 风格投票<br/>闭集选择, t=0.0<br/>必须匹配候选列表"]
        Summary["LLM 摘要生成<br/>Few-shot, t=0.3<br/>含推荐理由/优缺点/风险"]
        Fallback["_fallback_summary()<br/>规则模板降级"]
        Vote --> Summary
        Summary -.->|"LLM 不可用时"| Fallback
    end

    Top3 --> Vote

    Final["📋 最终推荐报告<br/>推荐结论 + 对比矩阵 + 拓扑图<br/>风险建议 + 组合推荐 + ADR"]

    Summary --> Final
    Fallback --> Final

    style Input fill:#e8f5e9,stroke:#2e7d32
    style L1 fill:#fff3e0,stroke:#e65100
    style L2 fill:#e3f2fd,stroke:#1565c0
    style L3 fill:#fce4ec,stroke:#c62828
    style L4 fill:#f3e5f5,stroke:#6a1b9a
    style Final fill:#e8f5e9,stroke:#2e7d32
```

> 图例: 橙色=Layer1规则引擎 / 蓝色=Layer2知识图谱(P2可选) / 红色=Layer3规则评分(始终运行) / 紫色=Layer4 LLM评估(L4可选)

### 在答辩中什么时候讲

**时间段**: 7:30-9:30（混合推理部分，约在第 8-9 页 PPT）

这是整个架构讲解中最核心的一张图——它把"规则保证下限，图谱增强关系，LLM 提升上限"这句话可视化了出来。

### 讲图的 1 分钟话术

> 这张图是系统最核心的**混合推理流程**——从自然语言需求到最终推荐报告的完整路径。
>
> 需求文本进来，先走 **Layer 1 规则引擎**——10 维关键词词典匹配（橙色区域），否定语义过滤，产出特征映射。如果关键词命中太少，触发 LLM 语义补全——但补全失败就跳过，不影响流程。
>
> 特征向量分流到两条路径——
>
> 左边 **Layer 2 知识图谱**（蓝色区域），通过 Neo4j Cypher 查询 HAS_QUALITY 关系，每个匹配属性 +2 分，但总分上限是规则得分的 50%。Neo4j 不可用时这条路径的贡献为 0。
>
> 右边 **Layer 3 规则评分**（红色区域），标签匹配 +2、学习权重 +1、特定规则 +1，始终运行。
>
> 两条路径通过 `blend_scores()` 融合，产出 Top 3 候选。
>
> 最后 **Layer 4 LLM 评估**（紫色区域）——LLM 从候选列表中投票选最佳，生成中文摘要。LLM 不可用时用规则模板降级。
>
> 注意四条横向色带的含义——层号越大，越"上层"（可选性越强）。Layer 1 和 Layer 3 是必须运行的，Layer 2 和 Layer 4 是可选增强。

### 老师可能追问

**Q: 为什么 Layer 2 图谱加分上限是 50%？**

> 防止图谱颠覆规则引擎的排序。举个极端例子——如果图谱给某个冷门风格加了 10 分，规则引擎只算了 2 分，最终 12 分排第一。但评委一看——"这个风格的 tags 和需求特征几乎不匹配，为什么排第一？"这就失去了可解释性。50% 上限确保：**图谱是辅助证据，不是替代判断。**

**Q: 如果 Layer 2 和 Layer 4 都不可用，Layer 1+3 能独自完成推荐吗？**

> 能。Layer 1 的特征提取 + Layer 3 的规则评分是完整链路。纯规则模式下的回归测试 20 条用例 100% 通过——Top3 完整率、主流覆盖率、推荐产出率、可解释率、矩阵完整率全部 100%。

---

## 图 6: 降级机制图

### Mermaid 代码

```mermaid
graph TB
    Request["📨 请求到达 API Gateway"]

    subgraph FullMode["Level 0: 全功能模式"]
        direction TB
        F1["✅ LangGraph 编排"]
        F2["✅ LLM 语义补全 + 投票 + 摘要"]
        F3["✅ Neo4j 图谱推理"]
        F4["✅ ADR 自动生成"]
        F5["✅ 重构建议 + LLM 润色"]
        F1 --> F2 --> F3 --> F4 --> F5
    end

    subgraph Degrade1["Level 1: LangGraph 降级"]
        D1["⚠ LangGraph 未安装或异常"]
        D1A["→ 自动回退手动编排 (httpx)"]
        D1B["功能完全等价, workflow_engine='manual'"]
        D1 --> D1A --> D1B
    end

    subgraph Degrade2["Level 2: LLM 调用降级"]
        D2["⚠ LLM 超时 / 返回异常 / API Key 未配置"]
        D2A["→ 语义补全: 静默跳过, 维持规则结果"]
        D2B["→ 风格投票: 返回 null, 不加分"]
        D2C["→ 摘要生成: _fallback_summary() 模板"]
        D2D["→ 重构润色: 使用规则模板原文"]
        D2 --> D2A
        D2 --> D2B
        D2 --> D2C
        D2 --> D2D
    end

    subgraph Degrade3["Level 3: Neo4j 降级"]
        D3["⚠ Neo4j 不可达"]
        D3A["→ auto/json 模式自动回退 JSON 后端"]
        D3B["→ POST /graph/match 返回 available: false"]
        D3C["→ 图谱加分 = 0, blend_scores() 不改变规则分"]
        D3 --> D3A --> D3B --> D3C
    end

    subgraph Degrade4["Level 4: 非关键服务降级"]
        D4["⚠ refactoring-agent 不可达"]
        D4A["→ refactoring_advice = {}, 非阻塞"]
        D4B["⚠ ADR 写入失败"]
        D4C["→ adr_status = 'failed', 主流程继续"]
        D4 --> D4A
        D4B --> D4C
    end

    subgraph CoreMode["Level Max: 纯规则模式 (核心链路)"]
        C1["🔒 规则引擎特征提取 — 始终运行"]
        C2["🔒 规则引擎评分排序 — 始终运行"]
        C3["🔒 JSON 知识库后端 — 始终可用"]
        C4["🔒 对比矩阵 + 拓扑图 — 始终产出"]
        C5["✅ 回归测试 20/20 通过, 5项指标全 100%"]
        C1 --> C2 --> C3 --> C4 --> C5
    end

    Request --> FullMode
    F1 -.->|"降级触发"| D1
    F2 -.->|"降级触发"| D2
    F3 -.->|"降级触发"| D3
    F4 -.->|"降级触发"| D4B
    F5 -.->|"降级触发"| D4
    D1 -.->|"继续降级"| D2
    D2 -.->|"继续降级"| D3
    D3 -.->|"继续降级"| CoreMode

    style FullMode fill:#e8f5e9,stroke:#2e7d32
    style Degrade1 fill:#fff8e1,stroke:#f9a825
    style Degrade2 fill:#fff3e0,stroke:#e65100
    style Degrade3 fill:#e3f2fd,stroke:#1565c0
    style Degrade4 fill:#f3e5f5,stroke:#6a1b9a
    style CoreMode fill:#ffebee,stroke:#c62828
```

### 在答辩中什么时候讲

**时间段**: 可以在两个地方使用——

1. **9:30-11:00**（LLM 集成方案部分，讲 LLM 降级时展示）
2. **12:30-14:00**（测试验证部分，讲降级可靠性时展示）

建议在 LLM 集成方案部分用这张图的前半部分（Level 0 → Level 2），在测试验证部分展示完整的降级矩阵。

### 讲图的 1 分钟话术

> 这张图展示了系统最重要的非功能特性——**多级降级**。
>
> 从上往下看，系统可以在 4 个层级独立降级——
>
> **Level 0 全功能模式**：LangGraph 编排 + LLM 全功能 + Neo4j 图谱 + ADR + 重构建议。输出最丰富的推荐报告。
>
> **Level 1 LangGraph 降级**：langgraph 未安装或运行异常时，自动回退手动编排。功能完全等价，只是 `workflow_engine` 从 "langgraph" 变成 "manual"。用户无感知。
>
> **Level 2 LLM 降级**：LLM 未配置或超时时，语义补全静默跳过，投票返回 null，摘要用规则模板。对比度最大——推荐报告从自然语言变成模板化文本，但核心推荐结论不变。
>
> **Level 3 Neo4j 降级**：Neo4j 不可用时自动回退 JSON 后端。图谱加分归零，`blend_scores()` 不改变规则分。候选排序完全由规则引擎决定。
>
> **最底层纯规则模式（红色）**：所有增强组件全部失效时，规则引擎 + JSON 知识库仍能独立输出包含推荐结论、对比矩阵、风险建议、拓扑图的完整报告。回归测试 20/20 验证了这一点。
>
> 设计原则是：**每一层降级都是在上一层基础上"减法"，而不是"断裂"**。用户在任何降级层级都能获得有意义的推荐结果。

### 老师可能追问

**Q: 如何保证某个降级层级不会悄悄生效而用户不知情？**

> 每个降级都有明确的前端反馈——
> - LangGraph 降级 → 状态栏显示 `workflow_engine: "manual"`
> - LLM 降级 → 摘要文本风格从自然语言变为模板化格式（用户可感知差异）
> - Neo4j 降级 → 图谱证据区块显示"无图谱证据"
> - 缓存降级（缓存后端出错）→ 正常执行完整流程，`cache_hit: false`
>
> 后端日志中也记录了每次降级事件：`logger.warning("langgraph not installed...")`、`logger.warning("LLM not configured...")` 等。

---

## 图 7: 可解释证据链图

### Mermaid 代码

```mermaid
graph TB
    Input["📝 用户需求<br/>'开发跨平台即时通讯系统...'"]

    subgraph L1["L1: 特征证据 — 确定性 (规则关键词)"]
        direction LR
        FeatHits["feature_hits<br/>━━━━━━━━<br/>high_concurrency: ['万人','高并发']<br/>real_time: ['实时','消息']<br/>reliability: ['可靠']<br/>scalability: ['扩展']"]
    end

    subgraph L2["L2: 匹配证据 — 确定性 (规则+图谱)"]
        direction LR
        RuleReasons["key_reasons (规则)<br/>━━━━━━━━<br/>+2 标签匹配 high_concurrency<br/>+2 标签匹配 real_time<br/>+2 标签匹配 reliability<br/>+2 标签匹配 scalability<br/>+1 特定规则 Event-Driven+高并发"]
        GraphEvid["graph_evidence (图谱)<br/>━━━━━━━━<br/>matched_attributes: 3个<br/>matched_scenarios: 实时消息<br/>related_risks: 事件一致性<br/>combinable: Microservices"]
    end

    subgraph L3["L3: 语义解释 — 概率性 (LLM)"]
        direction LR
        LLMSum["llm_summary<br/>━━━━━━━━<br/>1.推荐架构: 事件驱动架构(核心)<br/>  备选: 微服务、分层架构<br/>2.推荐理由:<br/>  - 消息驱动模式天然匹配IM场景<br/>  - 事件总线解耦生产者和消费者<br/>3.优缺点分析:<br/>  √ 高并发/松耦合/易扩展<br/>  × 事件一致性设计难度大<br/>4.风险与建议:<br/>  - 事件溯源复杂度高<br/>  - 建议事件schema版本管理"]
    end

    subgraph L4["L4: 决策记录 — 确定性 (持久化)"]
        direction LR
        ADR["ADR-YYYYMMDD-NNN<br/>━━━━━━━━<br/>adr_id: ADR-20260513-001<br/>requirement: 原始需求全文<br/>extracted_features: 完整特征<br/>candidates: Top3含分数理由<br/>recommended_style: Event-Driven<br/>decision_basis: 规则+LLM全记录<br/>risk_and_suggestions: 风险列表<br/>api_path: /adr/ADR-20260513-001"]
    end

    Matrix["📊 comparison_matrix<br/>3行 × 6列<br/>推荐类型/风格/得分/理由/优点/缺点"]

    Input --> FeatHits
    FeatHits --> RuleReasons
    FeatHits --> GraphEvid
    RuleReasons --> Matrix
    GraphEvid --> Matrix
    Matrix --> LLMSum
    LLMSum --> ADR

    style Input fill:#e8f5e9,stroke:#2e7d32
    style L1 fill:#fff3e0,stroke:#e65100
    style L2 fill:#e3f2fd,stroke:#1565c0
    style L3 fill:#f3e5f5,stroke:#6a1b9a
    style L4 fill:#fce4ec,stroke:#c62828
    style Matrix fill:#fff8e1,stroke:#f9a825
```

> 图例: 橙色=L1确定性证据 / 蓝色=L2确定性证据 / 紫色=L3概率性解释 / 红色=L4确定性持久化

### 在答辩中什么时候讲

**时间段**: 可在两个地方使用——

1. **7:30-9:30**（混合推理部分，讲完三条推理路径后展示证据链的层次结构）
2. **14:00-15:00**（总结部分，作为"可解释"亮点的可视化支撑）

建议在混合推理部分展示——它和"三层推理"的架构一脉相承，自然承接。

### 讲图的 1 分钟话术

> 这张图展示了系统最核心的非功能目标——**可解释性**。
>
> 一次推荐的四层证据链从下往上看——
>
> **L1 特征证据**（橙色）：确定性产出。`feature_hits` 记录每个被激活维度的命中关键词。评委可以质疑"高并发？凭什么？"——答案在 `feature_hits` 里："万人在线"命中了高并发词典。
>
> **L2 匹配证据**（蓝色）：确定性产出。`key_reasons` 逐条列出每个 +2/+1 的来源，`graph_evidence` 显示 Neo4j 图谱匹配到的属性和场景。评委可以质疑"Event-Driven 为什么 9 分？"——答案在 `key_reasons` 里：4 个标签 × 2 + 1 条特定规则 = 9。
>
> **L3 语义解释**（紫色）：概率性产出。LLM 生成的推荐理由、优缺点分析、风险建议。这一层最"像人写"，但确定性最低。所以 LLM 不可用时用模板替换，不影响 L1/L2 的确定性证据。
>
> **L4 决策记录**（红色）：确定性持久化产出。ADR 把整个决策链编码为一条可查询的记录，永久保存。评委可以通过 API 随时抽查历史上任何一次推荐。
>
> 四层证据链回答了评审中最核心的问题：**"你为什么推荐这个？"** 答案不在演示者的记忆里，在系统的输出字段里。

### 老师可能追问

**Q: L3 是概率性的，如果 LLM 摘要写错了怎么办？**

> L3 的定位是"语义解释"，不是"决策依据"。决策依据在 L1 和 L2 的确定性证据中。LLM 摘要写错了——比如把 Event-Driven 的优点说成了缺点——确实会影响阅读体验。我们通过 Few-shot Prompt（3 个示例）约束输出结构，但无法完全杜绝错误。这正是一开始把 LLM 放在系统边界外的原因——它对核心推荐的影响被限制在"摘要质量"层面，不会污染候选排序和评分。

**Q: ADR 数据量大了怎么办？**

> 当前的 ADR 存储是追加写入 JSON 文件——适合课程项目量级（几十到几百条）。生产环境需要换用真正的数据库并加分页索引。但 ADR 的 ID 格式（`ADR-YYYYMMDD-NNN`）已经内嵌了日期分区，便于按天归档。

---

## 附录: 图的绘制原则自查

| # | 原则 | 落实情况 |
|---|------|---------|
| 1 | 不画不存在的服务 | ✅ 所有 8 个容器均来自 `docker-compose.yml` |
| 2 | 虚线框标注可选组件 | ✅ LLM 和 Neo4j 均标为虚线 + 红色/蓝色标注 |
| 3 | 标注代码行数 | ✅ C4 Container 图每服务标注行数 |
| 4 | 标注超时时间 | ✅ UML 时序图每处 LLM 调用标注超时 |
| 5 | 标注端口号 | ✅ 所有微服务标注端口 |
| 6 | 区分"始终运行"和"可选" | ✅ 混合推理图用实线/虚线区分；降级图用颜色区分 |
| 7 | 非阻塞调用特殊标注 | ✅ Refactoring Agent 标注"非阻塞"，ADR 标注"非阻塞" |
| 8 | 降级路径清晰可追踪 | ✅ 降级图展示 Level 0→1→2→3→Max 的完整退化链路 |
| 9 | 证据链层次分明 | ✅ L1→L2→L3→L4 从确定性到概率性再到持久化 |

---

*本文档 7 张图均使用 Mermaid 语法，可在支持 Mermaid 的 Markdown 渲染器中直接渲染。所有组件名称、端口、行数均来自实际代码。*
