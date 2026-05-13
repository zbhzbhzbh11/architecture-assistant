# L06 · Matching Agent 规则与图谱匹配

> "规则是说一不二的法官，图谱是博览群书的资料员，LLM 投票是陪审团的参考意见。"

---

## 本节目标

学完本节，你将能够：

1. 解释 `score_style()` 的评分公式——基础分 + 规则分 + 学习权重
2. 说明 7 条硬编码规则的来源和设计考量
3. 理解 `blend_scores()` 中图谱加分的 50% 上限策略
4. 说出 Top 3 候选风格的选择逻辑（主流优先）

---

## 为什么需要这个模块

### 从"信号"到"候选"

上一步 requirements-agent 输出了特征信号：`{high_concurrency: true, real_time: true, ...}`

这组信号本身不直接等于架构推荐。你需要一个**评分引擎**来回答：

> "给定这些活跃特征，10 种架构风格谁最合适？为什么？"

这就是 matching-agent 的核心任务。

### 为什么是三层评分

如果只用一层评分（比如 LLM 直接说"选 Event-Driven"），你会面临三个问题：
- **不可解释**：为什么选它？
- **不可调优**：如果某个规则不合理，怎么改？
- **不可扩展**：如果新增一种风格，怎么让它被评估？

三层评分把问题拆解了：
- **基础评分**（规则引擎）：每个特征标签值 2 分 —— 透明
- **专业规则**（领域知识）：编码为 hard-coded rules —— 可调优
- **图谱增强**（关系推理）：从 Neo4j 中发现隐式关联 —— 可扩展

---

## 当前项目如何实现

### 评分公式（score_style）

```
最终得分 = 标签匹配分 + 学习权重分 + 专业规则分
         └─ +2/标签       └─ +1 (≥2次确认)  └─ +1/匹配规则
```

```python
# matching_agent/app/main.py:44-101
def score_style(style, features, learned_weights=None):
    score = 0
    reasons = []

    # ① 标签匹配: 每个匹配的 tag +2
    for tag in style.get("tags", []):
        if features.get(tag):
            score += 2
            reasons.append(f"matches feature: {tag}")

    # ② 学习权重: 基于历史反馈的特征-风格关联
    if learned_weights:
        for feat, is_active in features.items():
            if is_active and feat in learned_weights:
                w = learned_weights[feat].get(style_name, 0)
                if w >= 2:  # 至少 2 次确认才加分
                    score += 1
                    reasons.append(f"learned boost: {feat}->{style_name}")

    # ③ 专业规则: 7 条编码领域经验
    if style["name"] == "Event-Driven Architecture" and features.get("high_concurrency"):
        score += 1
        reasons.append("extra rule: high concurrency favors event-driven")
    # ... 共 7 条规则 ...

    return {"style": style["name"], "score": score, "reasons": reasons, ...}
```

### 7 条专业规则详解

| # | 规则 | 编码的领域知识 |
|---|------|-------------|
| 1 | 高并发 → Event-Driven +1 | 事件总线天然支持削峰填谷，同步调用链在高压下会出现雪崩 |
| 2 | 多团队 → Microservices +1 | Conway's Law：组织架构影响系统架构，独立团队需要独立部署 |
| 3 | 强一致性 → Layered +1 | 分层架构的核心领域层适合维护 ACID 事务边界 |
| 4 | 实时 + 数据密集 → Pipeline-Filter +1 | 流式处理天然适合分阶段管道 |
| 5 | 高并发 + 数据密集 → CQRS +1 | 读写分离可分别优化命令和查询性能 |
| 6 | 高并发 + 强一致性 → Microservices +1 | 微服务可将强一致性事务限定在服务内部 |

### 图谱证据融合（blend_scores）

规则评分之后，如果 Neo4j 可用，会从图谱中拉取额外证据：

```python
# matching_agent/app/graph_matcher.py:47-93
def blend_scores(rule_scored, graph_evidence):
    if not graph_evidence or not graph_evidence.get("ranked"):
        # Neo4j 不可用 → 原样返回，填充空字段
        for item in rule_scored:
            item.setdefault("graph_score", 0)
            ...
        return rule_scored

    for item in rule_scored:
        ge = graph_by_name.get(item["style"], {})
        g_score = ge.get("graph_score", 0)

        # 关键：图谱加分上限不超过规则分的 50%
        capped_bonus = min(g_score, max(1, rule_score // 2))
        item["score"] = rule_score + capped_bonus
        item["graph_reasons"] = [...]
```

**为什么要 cap？** 不让图谱主导评分。规则引擎是根基——它基于明确的特征标签和领域知识。图谱加分是锦上添花——它发现了特征-风格的隐式关联。但图谱数据可能不完整、可能有偏见。50% 的 cap 保证了图谱能增强推荐但不会推翻推荐。

### Top 3 候选选择逻辑

```python
# matching_agent/app/main.py:132-151
MAINSTREAM_STYLES = [
    "Layered Architecture",
    "Microservices",
    "Event-Driven Architecture",
]

# 策略：优先从主流风格中选有分数的
# 当所有信号为零时，返回主流风格作为基线对比
if all(item["score"] == 0 for item in mainstream_ranked):
    top3 = mainstream_ranked[:3]  # 三种主流风格全返回
else:
    # 1. 主流风格 + 有分数的优先
    # 2. 其他高分非主流风格补入
    # 3. 保证始终返回 3 个候选
```

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [matching_agent/app/main.py:44-67](../services/matching_agent/app/main.py#L44-L67) | 基础评分 + 学习权重 |
| [matching_agent/app/main.py:64-86](../services/matching_agent/app/main.py#L64-L86) | 7 条专业规则 |
| [matching_agent/app/main.py:88-101](../services/matching_agent/app/main.py#L88-L101) | 返回值结构 |
| [matching_agent/app/main.py:103-170](../services/matching_agent/app/main.py#L103-L170) | `/match` 端点完整逻辑 |
| [matching_agent/app/graph_matcher.py:47-93](../services/matching_agent/app/graph_matcher.py#L47-L93) | `blend_scores()` 融合策略 |
| [matching_agent/app/graph_matcher.py:15-45](../services/matching_agent/app/graph_matcher.py#L15-L45) | `fetch_graph_evidence()` 图谱调用 |

---

## 面试官可能怎么问

**Q1: 为什么是 +2 和 +1？不是 +5 和 +3？**

> 评分体系的关键不是绝对值，而是**相对排序**。+2/+1 的设计保证了：
> - 标签匹配（确定性高）的权重大于专业规则（经验判断）
> - 专业规则的权重大于学习权重（需要积累确认）
> - 即使所有规则都命中（最多 +7），标签匹配仍然是主导因素
>
> 如果全部放大 5 倍变 +10/+5，排序不变。这就是为什么评分体系设计时关注的是**相对权重**而非绝对数值。

**Q2: 7 条规则为什么是 7 条？怎么不是 70 条？**

> 规则引擎的一个陷阱是"过度规则化"——规则越多，相互冲突的可能性越大。7 条规则覆盖了 10 个特征维度中最常见、最明确的关联关系。比如"高并发 → Event-Driven +1"有充分的架构理论支撑（事件总线削峰填谷），而"安全性 → Microservices +1"就不够普遍（安全性可以通过多种架构实现）。
>
> 过少（≤3 条）则规则不痛不痒，过多（≥15 条）则规则之间打架。7 条是目前的知识覆盖度和工程复杂度之间的平衡点。

**Q3: 如果 Neo4j 不可用，评分会差多少？**

> 评分差了图谱加分部分——最多每条推荐差规则分的 50%。但 Neo4j 不可用时，matching-agent 仍然有规则评分（始终可用），输出的是基于规则的候选人。图谱是用来**增强**而非**替代**的。

---

## 简历上如何表达

> 实现三层混合评分引擎：规则引擎主导（标签匹配 + 7 条架构规则 + 学习权重），Neo4j 图谱推理增强（HAS_QUALITY 关系遍历，加分上限 50%），主流风格优先策略保证候选集质量。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| 评分公式 | 标签 +2、规则 +1、学习权重 +1（≥2 确认） |
| 规则数量 | 7 条，覆盖高并发/多团队/强一致/数据密集等关键场景 |
| 图谱 cap | 图谱加分 ≤ 规则分 50%，防止图谱主导 |
| Neo4j 降级 | 不可用时规则引擎独立工作，图谱字段填空 |
| 主流优先 | Layered/Microservices/Event-Driven 优先进入候选 |
