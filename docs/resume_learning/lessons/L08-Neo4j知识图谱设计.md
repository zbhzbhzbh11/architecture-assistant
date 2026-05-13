# L08 · Neo4j 知识图谱设计

> "关系型数据库存的是'是什么'，知识图谱存的是'与什么有关'。"

---

## 本节目标

学完本节，你将能够：

1. 画出 Neo4j 图模型：6 种节点 + 6 种关系
2. 解释 `graph_match()` 的 Cypher 查询逻辑
3. 说明 JSON fallback 的工作方式（`KNOWLEDGE_BACKEND=auto`）
4. 回答："为什么不全部用 Neo4j？"

---

## 为什么需要知识图谱

### 从"表格"到"关系网"

假设你有 10 种架构风格和 10 个质量属性。用 JSON 存储，你可以快速查出"Event-Driven Architecture 有哪些标签"——但查不出"哪些风格和 Event-Driven 可以组合使用"、"高并发场景有哪些风险"。

这就是图的优势：**关系是头等公民**。在 Neo4j 中，你不需要 JOIN 表来发现关联——关系直接就存储在边上。

```
(Event-Driven Architecture) -[:HAS_QUALITY]-> (高并发)
(Event-Driven Architecture) -[:SUITABLE_FOR]-> (实时消息系统)
(Event-Driven Architecture) -[:HAS_RISK]-> (事件一致性设计难度大)
(Event-Driven Architecture) -[:COMPLEMENTS]-> (CQRS)
```

一条 Cypher 查询就能遍历所有关联，无需定义外键、无需多表 JOIN。

---

## 当前项目如何实现

### 图模型设计

```
┌──────────────────────────────────────────────────────────┐
│                    图模型全景                              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│   ArchitectureStyle ──[:HAS_QUALITY]──▶ QualityAttribute  │
│         │                                      ▲          │
│         │                                      │          │
│         ├──[:SUITABLE_FOR]──▶ Scenario        │          │
│         ├──[:HAS_RISK]─────▶ Risk             │          │
│         └──[:COMPLEMENTS]──▶ ArchitectureStyle │          │
│                                                  │        │
│   ADR ──[:RECOMMENDS]──▶ ArchitectureStyle       │        │
│   ADR ──[:BASED_ON]───▶ QualityAttribute ────────┘        │
│                                                          │
│   Feedback (独立节点)                                      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

| 节点类型 | 数量 | 说明 |
|---------|------|------|
| **ArchitectureStyle** | 10 | 10 种架构风格（Layered, Microservices, EDA...） |
| **QualityAttribute** | 10 | 10 个质量属性维度 |
| **Scenario** | ~12 | 典型场景（real-time messaging, enterprise app...） |
| **Risk** | ~6 | 常见风险 |
| **ADR** | 累积 | 每次推荐的决策记录 |
| **Feedback** | 累积 | 用户反馈 |

| 关系类型 | 含义 | 方向 |
|---------|------|------|
| HAS_QUALITY | 该风格具备此质量属性 | Style → Quality |
| SUITABLE_FOR | 该风格适合此场景 | Style → Scenario |
| HAS_RISK | 该风格有此风险 | Style → Risk |
| COMPLEMENTS | 该风格可与另一风格组合 | Style → Style |
| RECOMMENDS | ADR 推荐了该风格 | ADR → Style |
| BASED_ON | ADR 基于此质量属性 | ADR → Quality |

### 核心查询：graph_match()

这是整个知识图谱最核心的查询，在 matching-agent 调用图谱证据时触发：

```python
# knowledge_base/app/graph_repository.py:247-319
def graph_match(features):
    active_features = [k for k, v in features.items() if v]

    for feat in active_features:
        # 查找通过 HAS_QUALITY 关联到此 quality attribute 的架构风格
        result = session.run("""
            MATCH (q:QualityAttribute {name: $feat})
            MATCH (s:ArchitectureStyle)-[:HAS_QUALITY]->(q)
            OPTIONAL MATCH (s)-[:SUITABLE_FOR]->(sc:Scenario)
            OPTIONAL MATCH (s)-[:HAS_RISK]->(r:Risk)
            OPTIONAL MATCH (s)-[:COMPLEMENTS]->(c:ArchitectureStyle)
            RETURN s.name AS style, s.name_zh AS style_zh,
                   collect(DISTINCT q.name) AS qualities,
                   collect(DISTINCT sc.name) AS scenarios,
                   collect(DISTINCT r.name) AS risks,
                   collect(DISTINCT c.name) AS complements
        """, {"feat": feat})

        # 每个匹配的质量属性 +2 图谱分
        entry["graph_score"] += 2
```

**查询逻辑**：对于每个活跃特征（如 `high_concurrency`），找到所有具有此质量属性的风格，同时拉取关联的场景、风险和可组合风格。然后按 `graph_score` 降序返回。

### 双后端调度：`_repo()` 统一入口

```python
# knowledge_base/app/main.py:21-51
BACKEND = os.getenv("KNOWLEDGE_BACKEND", "json")  # json | neo4j | auto

def _repo(method_name, *args, **kwargs):
    if _prefer_graph():  # BACKEND in ("neo4j", "auto")
        result = getattr(GraphRepository, method_name)(*args, **kwargs)
        if result is not None:
            return result
        if _require_graph():  # BACKEND == "neo4j"
            raise RuntimeError("Neo4j required but unavailable")
        # auto 模式: fallback to JSON
    return getattr(JsonRepository, method_name)(*args, **kwargs)
```

**三种模式**：

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `json` | 始终用 JSON 文件，不碰 Neo4j | 本地开发，零外部依赖 |
| `neo4j` | 始终用 Neo4j，不可用则 503 | 展示图谱推理能力 |
| `auto` | 优先 Neo4j，不可用自动 JSON | 答辩演示（有图时展示，无图时也能跑） |

**关键设计**：GraphRepository 和 JsonRepository 实现了**相同的方法签名**——`get_styles()`、`add_style()`、`get_feedback()`、`add_adr()`... 每种方法在两个 Repository 中都有对应的实现。`_repo()` 调度函数在两个实现之间透明切换。

### 图数据初始化

```bash
# 首次启动后执行
docker compose exec knowledge-base python init/init_neo4j.py
```

初始化脚本负责：
1. 读取 `architecture_styles.json` 的数据
2. 在 Neo4j 中创建 ArchitectureStyle → QualityAttribute → Scenario → Risk 的节点和关系
3. 确保每个风格的 tags/pros/cons/best_for 都正确映射为图结构

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [knowledge_base/app/graph_repository.py:22-48](../services/knowledge_base/app/graph_repository.py#L22-L48) | `_get_driver()` Neo4j 连接 |
| [knowledge_base/app/graph_repository.py:247-319](../services/knowledge_base/app/graph_repository.py#L247-L319) | `graph_match()` 核心查询 |
| [knowledge_base/app/graph_repository.py:50-96](../services/knowledge_base/app/graph_repository.py#L50-L96) | `get_styles()` 图→JSON |
| [knowledge_base/app/json_repository.py:39-54](../services/knowledge_base/app/json_repository.py#L39-L54) | `get_styles()` JSON 读取 |
| [knowledge_base/app/main.py:21-51](../services/knowledge_base/app/main.py#L21-L51) | `_repo()` 双后端调度 |
| [knowledge_base/init/init_neo4j.py](../services/knowledge_base/init/init_neo4j.py) | Neo4j 初始化脚本 |

---

## 面试官可能怎么问

**Q1: 为什么用图数据库而不是关系型数据库？**

> 架构知识天然是图状的。一个架构风格关联多个质量属性，质量属性被多个风格共享，风格之间还可以互组合。用关系型数据库，这种"多对多"关系需要关联表，查询需要多表 JOIN。用图数据库，`(s)-[:HAS_QUALITY]->(q)` 一个 Cypher 语句就能遍历所有关联，更直观也更高效。

**Q2: Neo4j 在你的项目中是必需的吗？**

> 不是。我设计了 JSON fallback 机制（`KNOWLEDGE_BACKEND=auto`）。Neo4j 可用时它提供图推理增强评分；Neo4j 不可用时系统自动降级到 JSON 文件存储，核心推荐链路不受影响。这是一个务实的工程选择——展示图谱推理能力的同时不引入强依赖。

**Q3: 你的图模型只有 6 节点 + 6 关系，是不是太小了？**

> 确实比较轻量。但这是有意为之——10 种风格和 10 个质量属性之间最多 100 条 HAS_QUALITY 边，关系密度已经足够支撑推理。如果有 100 种风格，图模型的优势会更明显。当前规模下，图和 JSON 的差异不大——但图的**框架**已经就绪，数据量增加时不需要改代码。

---

## 简历上如何表达

> 设计 Neo4j 知识图谱模型（6 节点类型 + 6 关系类型），实现 HAS_QUALITY/COMPLEMENTS 关系遍历推理；通过 KNOWLEDGE_BACKEND 环境变量支持 json/neo4j/auto 三种存储模式，Neo4j 不可用时自动 fallback JSON 保证零外部依赖。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| 为什么用图 | 架构知识天然是关系网络 |
| 图模型规模 | 6 节点 + 6 关系，当前为轻量实现 |
| 核心查询 | `graph_match()` HAS_QUALITY 遍历 |
| 双后端 | GraphRepository 和 JsonRepository 相同接口 |
| 调度机制 | `_repo()` 根据 BACKEND 环境变量透明切换 |
| 局限性 | 数据量小（10 风格），图优势尚未完全体现 |
