"""图谱关系匹配器 —— 调用 knowledge-base 的 Neo4j 图谱接口获取关系证据.

当 Neo4j 不可用时返回空结果, 由 main.py 回退到纯规则引擎评分.
所有新增字段均为增量, 不删除或修改原有 score_style() 的输出.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("matching-agent.graph")


async def fetch_graph_evidence(
    knowledge_base_url: str,
    features: Dict[str, bool],
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """调用 knowledge-base POST /graph/match 获取图谱匹配证据.

    Returns:
        None  — 图谱不可用, 调用者应回退规则引擎
        dict  — {"available": True, "ranked": [...], "active_features": [...]}
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.post(
                f"{knowledge_base_url}/graph/match",
                json={"features": features},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("available"):
                logger.info("Graph match not available: %s", data.get("reason", "unknown"))
                return None
            logger.info(
                "Graph match returned %d styles for %d active features",
                len(data.get("ranked", [])),
                len(data.get("active_features", [])),
            )
            return data
    except Exception as e:
        logger.warning("Graph match request failed: %s", e)
        return None


def blend_scores(
    rule_scored: List[Dict[str, Any]],
    graph_evidence: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """将规则引擎评分与图谱证据融合.

    策略:
      - graph_score 作为加权加分 (每个匹配属性 +2, 最多不超过规则得分的 50%)
      - 图谱证据字段 (graph_reasons, matched_attributes 等) 追加到候选
      - 无图谱证据时原样返回 rule_scored
    """
    if not graph_evidence or not graph_evidence.get("ranked"):
        # 无图谱证据: 填充空字段, 保持结构兼容
        for item in rule_scored:
            item.setdefault("graph_score", 0)
            item.setdefault("graph_reasons", [])
            item.setdefault("matched_attributes", [])
            item.setdefault("matched_scenarios", [])
            item.setdefault("related_risks", [])
            item.setdefault("combinable_styles", [])
        return rule_scored

    graph_by_name: Dict[str, Dict[str, Any]] = {
        g["style"]: g for g in graph_evidence["ranked"]
    }

    for item in rule_scored:
        name = item["style"]
        ge = graph_by_name.get(name, {})
        g_score = ge.get("graph_score", 0)

        # 图谱加分: 上限不超过规则得分的 50% (避免图谱主导)
        rule_score = item.get("score", 0)
        capped_bonus = min(g_score, max(1, rule_score // 2))

        item["score"] = rule_score + capped_bonus
        item["graph_score"] = g_score
        item["graph_reasons"] = [
            f"graph match: quality attribute '{a}'" for a in ge.get("matched_attributes", [])
        ]
        item["matched_attributes"] = ge.get("matched_attributes", [])
        item["matched_scenarios"] = ge.get("matched_scenarios", [])
        item["related_risks"] = ge.get("related_risks", [])
        item["combinable_styles"] = ge.get("combinable_styles", [])

    return rule_scored
