"""架构组合推荐器 — 在单一风格推荐基础上生成组合架构候选.

组合评分 = 组成风格分数之和 + 特征覆盖互补加分 + CAN_COMBINE_WITH 加分 - 复杂度惩罚
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("matching-agent.combo")

COMPLEXITY_PENALTY_PER_LEVEL = 1  # 每个复杂度级别的惩罚分


async def fetch_combinations(knowledge_base_url: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """从 knowledge-base 获取架构组合列表."""
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.get(f"{knowledge_base_url}/combinations")
            resp.raise_for_status()
            return resp.json().get("combinations", [])
    except Exception as e:
        logger.warning(f"Failed to fetch combinations: {e}")
        return []


def score_combination(
    combo: Dict[str, Any],
    scored_styles: Dict[str, Dict[str, Any]],
    features: Dict[str, bool],
    graph_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """为单个架构组合打分.

    Args:
        combo: 组合定义 (styles, tags, complexity_penalty, synergy, ...)
        scored_styles: 已评分单一风格 {name: {score, reasons, ...}}
        features: 活跃特征
        graph_evidence: 图谱证据 (含 combinable_styles)
    """
    component_names = combo.get("styles", [])
    components = [scored_styles.get(n) for n in component_names if scored_styles.get(n)]

    if not components:
        return {**combo, "combo_score": 0, "components": [], "reasons": []}

    # 1. 组成风格分数之和
    base_sum = sum(c.get("score", 0) for c in components)
    reasons: List[str] = [f"component scores sum: {base_sum}"]

    # 2. 特征覆盖互补加分
    covered_features: set = set()
    for comp in components:
        for attr in comp.get("matched_attributes", []):
            covered_features.add(attr)
    for tag in combo.get("tags", []):
        if features.get(tag):
            covered_features.add(tag)
    coverage_bonus = len(covered_features) * 1  # 每个被覆盖的特征 +1
    reasons.append(f"feature coverage bonus: +{coverage_bonus} ({len(covered_features)} dimensions)")

    # 3. 图谱 CAN_COMBINE_WITH 加分
    graph_bonus = 0
    if graph_evidence and graph_evidence.get("ranked"):
        for ge in graph_evidence["ranked"]:
            combinable = ge.get("combinable_styles", [])
            for cn in component_names:
                if cn in combinable:
                    graph_bonus += 2  # 图谱确认可组合 +2
        if graph_bonus:
            reasons.append(f"graph CAN_COMBINE_WITH bonus: +{graph_bonus}")

    # 4. 复杂度惩罚
    penalty = combo.get("complexity_penalty", 1) * COMPLEXITY_PENALTY_PER_LEVEL
    reasons.append(f"complexity penalty: -{penalty}")

    final_score = base_sum + coverage_bonus + graph_bonus - penalty

    return {
        "combination_name": combo["name"],
        "combination_name_zh": combo.get("name_zh", combo["name"]),
        "combo_score": max(0, final_score),
        "components": [c.get("style", "") for c in components],
        "component_details": [
            {"style": c.get("style", ""), "style_zh": c.get("style_zh", ""), "score": c.get("score", 0)}
            for c in components
        ],
        "synergy": combo.get("synergy", ""),
        "synergy_zh": combo.get("synergy_zh", ""),
        "best_for": combo.get("best_for", []),
        "best_for_zh": combo.get("best_for_zh", []),
        "tags": combo.get("tags", []),
        "complexity_penalty": combo.get("complexity_penalty", 1),
        "topology_mermaid": combo.get("topology_mermaid", ""),
        "reasons": reasons,
    }


def rank_combinations(
    combinations: List[Dict[str, Any]],
    scored_styles: Dict[str, Dict[str, Any]],
    features: Dict[str, bool],
    graph_evidence: Optional[Dict[str, Any]] = None,
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """对所有组合评分并排序, 返回 Top N."""
    scored = [
        score_combination(c, scored_styles, features, graph_evidence)
        for c in combinations
    ]
    scored.sort(key=lambda x: x["combo_score"], reverse=True)
    return scored[:top_n]
