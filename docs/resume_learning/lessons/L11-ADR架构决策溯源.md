# L11 · ADR 架构决策溯源

> "代码会过时，文档会丢失，但决策记录是架构演化的化石。"

---

## 本节目标

学完本节，你将能够：

1. 解释 ADR（Architecture Decision Record）的概念和价值
2. 说明本项目中 ADR 的自动生成、存储和查询流程
3. 理解 ADR 写入失败为什么不阻塞推荐
4. 回答："你的 ADR 和手写 ADR 有什么区别？"

---

## 为什么需要 ADR

### 一个"病例档案"的类比

你去医院看病，医生开了药。三个月后你复诊，另一个医生接诊。如果上一个医生没有写病历，新医生需要从头问一遍——"你上次什么症状？用了什么药？为什么用这个药？"

软件架构是一样的。三个月前的技术决策——"为什么选了 Event-Driven 而不是 Microservices"——如果不记录下来，三个月后团队成员换了，没人知道当初为什么这样选。ADR 就是架构的"病历"。

### ADR 的四要素

一个标准的 ADR 包含四个问题：

| 要素 | 含义 | 本项目对应 |
|------|------|----------|
| **决策是什么** | 选了哪个方案 | `recommended_style` |
| **为什么这样选** | 决策依据 | `decision_basis`（规则理由 + LLM 摘要） |
| **有什么备选** | 被排除的方案 | `alternative_styles` |
| **有什么风险** | 已知的 trade-off | `risk_and_suggestions` |

---

## 当前项目如何实现

### 自动生成流程

```
用户请求
    │
    ▼
api-gateway 编排
    │
    ▼
evaluation-agent evaluate()
    │
    ├─── 生成推荐报告 (正常流程)
    │
    └─── ADR 自动写入 ──── try/except ──── 失败不阻塞!
              │
              ▼
         knowledge-base
         POST /adr
              │
              ▼
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
JSON 存储            Neo4j 同步
(主存储)             (可选增强)
```

### ADR 内容结构

每次推荐完成后，evaluation-agent 自动向 knowledge-base 发起 ADR 写入：

```python
# evaluation_agent/app/main.py:350-392
async with httpx.AsyncClient(timeout=5.0) as adr_client:
    adr_resp = await adr_client.post(
        f"{KNOWLEDGE_BASE_URL}/adr",
        json={
            "requirement": payload.requirement,
            "extracted_features": payload.features,
            "candidates": [c for c in ranked[:3]],
            "recommended_style": best_style,
            "recommended_style_zh": best_zh,
            "alternative_styles": [c.get("style") for c in ranked[1:]],
            "decision_basis": report["decision_basis"],
            "risk_and_suggestions": risk_info,
            "graph_evidence": graph_evidence,
        },
    )
```

一条 ADR 包含的完整信息：

| 字段 | 内容 |
|------|------|
| `adr_id` | `ADR-20260513-001`（自动生成） |
| `timestamp` | 推荐时间 |
| `requirement` | 用户原始需求 |
| `extracted_features` | 提取的 10 维特征信号 |
| `candidates` | Top 3 候选风格 |
| `recommended_style` | 最终推荐 |
| `alternative_styles` | 备选方案 |
| `decision_basis` | 规则引擎理由 + LLM 摘要 + LLM 投票 |
| `risk_and_suggestions` | 风险与缓解建议 |
| `graph_evidence` | 图谱匹配的质量属性/场景/可组合风格 |

### ADR ID 设计

```python
# knowledge_base/app/json_repository.py:167
adr_id = f"ADR-{datetime.now().strftime('%Y%m%d')}-{len(records) + 1:03d}"
# 示例: ADR-20260513-001, ADR-20260513-002, ...
```

**设计考量**：日期前缀 + 序号，按日期归类、按序号排列。简单但有效。

### 双存储：JSON 主存储 + Neo4j 同步

**JSON 存储**（主路径，始终可用）：
```python
# json_repository.py:158-175
def add_adr(adr_data):
    records = load_json(ADR_PATH)  # 读取已有记录
    adr_id = f"ADR-{today}-{len(records)+1:03d}"
    adr_data["adr_id"] = adr_id
    records.append(adr_data)
    save_json(ADR_PATH, records)
    return {"adr_id": adr_id, "total": len(records), "status": "ok"}
```

**Neo4j 同步**（可选增强）：
```python
# graph_repository.py:332-377
# 创建 ADR 节点
session.run("CREATE (a:ADR {adr_id: $adr_id, timestamp: $ts, ...})")

# 关联到 ArchitectureStyle
session.run("MATCH (a:ADR), (s:ArchitectureStyle {name: $style}) MERGE (a)-[:RECOMMENDS]->(s)")

# 关联到 QualityAttribute
for feat, active in features.items():
    if active:
        session.run("MATCH (a:ADR) MERGE (q:QualityAttribute {name: $feat}) MERGE (a)-[:BASED_ON]->(q)")
```

ADR 在图数据库中成为了连接需求、风格和属性的**枢纽节点**。

### 容错设计

```python
# evaluation_agent/app/main.py:350-392
try:
    # ADR 写入...
    adr_status = "ok"
except Exception as e:
    adr_status = "failed"
    logger.warning(f"ADR generation failed (non-fatal): {e}")

report["adr"] = {"adr_id": adr_id, "adr_status": adr_status}
```

**ADR 写入失败不阻塞推荐**。用户仍然拿到完整的推荐报告——只是 `adr_status` 为 `"failed"`。这是有意为之：AD 记录是"锦上添花"，不是核心功能。

### ADR 查询 API

| 端点 | 说明 |
|------|------|
| `GET /adr?limit=20` | 最近 20 条 ADR 列表 |
| `GET /adr/{adr_id}` | 单条 ADR 详情 |

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [evaluation_agent/app/main.py:350-392](../services/evaluation_agent/app/main.py#L350-L392) | ADR 自动触发 |
| [knowledge_base/app/json_repository.py:158-196](../services/knowledge_base/app/json_repository.py#L158-L196) | ADR JSON 存储 |
| [knowledge_base/app/graph_repository.py:332-377](../services/knowledge_base/app/graph_repository.py#L332-L377) | ADR Neo4j 同步 |
| [knowledge_base/app/main.py:186-227](../services/knowledge_base/app/main.py#L186-L227) | ADR API 端点 |

---

## 面试官可能怎么问

**Q1: 什么是 ADR？为什么要在你的项目中加这个？**

> ADR 是 Architecture Decision Record，架构决策记录。它的核心思想是：每个重要的架构决策都应该记录下来——选了哪个方案、为什么选、还有什么备选、有什么风险。
>
> 我的项目自动生成 ADR，因为推荐本身就是一次架构决策。每次推荐完成后，系统自动把需求、候选、推荐理由、风险评估写入 ADR。这样一段时间后，你可以回顾所有的推荐历史，发现模式——比如"Event-Driven 在哪些场景下被推荐最多？准确率如何？"

**Q2: ADR 写入失败了会影响推荐吗？**

> 不会。ADR 写入在 `try/except` 中执行，失败了只记录 `adr_status: "failed"`，推荐报告正常返回。这是有意为之——ADR 是决策的"事后记录"，不是推荐流程的必要环节。

**Q3: 你的 ADR 和工业界的 ADR 有什么区别？**

> 工业界的 ADR 通常是手写的——架构师主动记录重要决策。我的 ADR 是自动生成的——每次推荐触发一次写入。适用场景不同：工业界 ADR 面向关键架构变更（频率低、影响大），我的 ADR 面向推荐请求（频率高、每次记录）。但格式和要素是兼容的——都包含决策、依据、备选、风险。

---

## 简历上如何表达

> 实现 ADR 自动生成机制：每次推荐完成后自动将需求、特征、候选、推荐理由、风险分析写入决策记录；JSON 主存储 + Neo4j 同步，ADR ID 格式 ADR-YYYYMMDD-NNN；写入失败不阻塞推荐。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| ADR 价值 | 记录"选了谁、为什么、还有什么、有什么风险" |
| 自动生成 | evaluate() 完成后自动触发，无需手动 |
| ADR ID | ADR-YYYYMMDD-NNN，按日期+序号 |
| 双存储 | JSON 主存储 + Neo4j 同步（可选） |
| 容错 | ADR 写入失败不阻塞推荐 |
| 诚实标注 | 当前为批量自动生成，非工业级手写 ADR |
