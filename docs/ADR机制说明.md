# ADR (Architecture Decision Record) 机制说明

## 1. 概述

ADR (Architecture Decision Record) 是系统每次推荐完成后自动生成的架构决策记录。它完整存档了从需求输入到最终推荐的整个推理过程，为后续审计、对比分析和决策溯源提供了可追溯的证据链。

## 2. ADR 内容

每条 ADR 包含以下字段：

| 字段 | 说明 |
|------|------|
| `adr_id` | 唯一编号，格式 `ADR-YYYYMMDD-NNN` |
| `timestamp` | 决策时间 |
| `requirement` | 原始需求文本 |
| `extracted_features` | 提取的 10 维特征布尔值 |
| `candidates` | Top 3 候选架构风格及评分 |
| `recommended_style` | 最终推荐的架构风格 |
| `recommended_style_zh` | 中文风格名称 |
| `alternative_styles` | 备选架构列表 |
| `decision_basis` | 决策依据（规则引擎理由 + LLM 摘要 + LLM 投票） |
| `risk_and_suggestions` | 风险点与缓解建议 |
| `graph_evidence` | 图谱匹配证据（质量属性、场景、可组合风格） |

## 3. 存储机制

```
POST /api/v1/recommend
  │
  ▼
evaluation-agent 完成评估
  │
  ├─ POST /adr → knowledge-base
  │     ├─ 主存储: JSON 文件 (data/adr_records.json)
  │     └─ 同步 (可选): Neo4j
  │           ├─ (:ADR)-[:RECOMMENDS]->(:ArchitectureStyle)
  │           └─ (:ADR)-[:BASED_ON]->(:QualityAttribute)
  │
  └─ 失败 → final_report.adr.adr_status = "failed"
             (不阻塞推荐主链路)
```

## 4. API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/adr` | 保存一条 ADR（由 evaluation-agent 自动调用） |
| GET | `/adr?limit=20` | 列出最近的 ADR |
| GET | `/adr/{adr_id}` | 查看单条 ADR 详情 |

## 5. 使用示例

```bash
# 查看最近 5 条 ADR
curl http://localhost:8004/adr?limit=5

# 查看特定 ADR
curl http://localhost:8004/adr/ADR-20260513-001
```

## 6. 前端展示

每次推荐完成后，前端结果页面的 ADR 区域显示：

- ADR 编号（如 ADR-20260513-003）
- 状态标记（已记录 / 记录失败）
- "查看决策溯源" 链接

## 7. 故障容错

- ADR 写入失败 **不会** 导致推荐接口失败
- 失败时 `final_report.adr.adr_status = "failed"`
- 推荐结果仍然正常返回
- ADR 仅在推荐主链路完成后异步写入

## 8. Neo4j 图模型

当 Neo4j 可用时，ADR 同时写入图数据库：

```
(:ADR {adr_id, timestamp, requirement, recommended_style})
  │
  ├──[:RECOMMENDS]──→ (:ArchitectureStyle {name})
  │
  └──[:BASED_ON]───→ (:QualityAttribute {name})
       (多条，每个活跃特征一条)
```

这允许通过 Cypher 查询所有推荐过某风格的 ADR：
```cypher
MATCH (a:ADR)-[:RECOMMENDS]->(s:ArchitectureStyle {name: "Microservices"})
RETURN a.adr_id, a.requirement, a.timestamp
ORDER BY a.timestamp DESC
```
