"""图谱评分融合模块 — 纯函数，从 matching-agent/graph_matcher.py 提取。

【为什么图谱加分有 50% 上限】
防止 Neo4j 图谱证据过度影响推荐结果。
规则引擎是确定性评分, 图谱是辅助推理, LLM 是语义理解。
三层驱动模式中, 规则引擎是"主" (保证底线), 图谱和 LLM 是"辅" (提升上限)。

【Neo4j 不可用时的降级】
graph_evidence 为 None → blend_scores() 保持原评分,
仅填充空图字段 (graph_score=0, matched_attributes=[] 等)。
"""

from typing import Any, Dict, List, Optional


def blend_scores(
    rule_scored: List[Dict[str, Any]],
    graph_evidence: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """将规则引擎评分与图谱证据融合.

    策略:
      - graph_score 作为加权加分, 上限不超过规则得分的 50%
      - 无图谱证据时保留原分, 只填充空 graph 字段保持结构兼容
      - 每个匹配的质量属性映射为一条 graph_reasons 记录

    上限设计依据: 图谱证据反映的是"理论上适合", 规则引擎反映的是
    "用户需求直接匹配". 后者权重应始终高于前者.
    """
    if not graph_evidence or not graph_evidence.get("ranked"):
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

        rule_score = item.get("score", 0)
        capped_bonus = min(g_score, max(1, rule_score // 2))

        item["score"] = rule_score + capped_bonus
        item["graph_score"] = g_score
        item["graph_reasons"] = [
            f"graph match: quality attribute '{a}'"
            for a in ge.get("matched_attributes", [])
        ]
        item["matched_attributes"] = ge.get("matched_attributes", [])
        item["matched_scenarios"] = ge.get("matched_scenarios", [])
        item["related_risks"] = ge.get("related_risks", [])
        item["combinable_styles"] = ge.get("combinable_styles", [])

    return rule_scored
