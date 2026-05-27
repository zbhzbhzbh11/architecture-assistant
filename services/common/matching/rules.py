"""规则引擎评分模块 — 纯函数，从 matching-agent 提取为共享模块。

【评分公式 — score_style()】
总分 = 标签基础分 (+2/项) + 学习权重分 (+1/≥2次确认) + 特定规则加成 (+1/条)

【Top 3 选择策略 — select_top3()】
  A: 全部主流零分 → 返回 3 个主流作为基线
  B: 主流有正分 → 先收主流, 再按分补齐其他风格
  C: 尚未满 → 从非主流列表补满
"""

from typing import Any, Dict, List

# 特征维度中文标签 (用于可解释性理由)
_FEAT_ZH = {
    "high_concurrency": "高并发", "real_time": "实时性", "reliability": "可靠性",
    "scalability": "可扩展性", "complex_business": "复杂业务", "strict_consistency": "强一致性",
    "deployment_constraint": "部署约束", "data_intensive": "数据密集型",
    "team_size_large": "多团队协作", "security": "安全性",
    "simple_crud": "极简业务", "resource_constrained": "资源受限",
}

# 三大主流架构 — Top 3 必须包含至少一种
MAINSTREAM_STYLES = [
    "Layered Architecture",
    "Microservices",
    "Event-Driven Architecture",
]


def score_style(style: Dict[str, Any], features: Dict[str, bool],
                learned_weights: Dict[str, Dict[str, int]] | None = None,
                llm_disputed: Dict[str, bool] | None = None) -> Dict[str, Any]:
    """规则引擎评分 — 四层: 标签匹配 + 学习权重 + 特定规则 + 非对称惩罚.
    llm_disputed: LLM 争议的特征 → 降权为 +1 (原 +2).
    reasons 数组记录每条加分原因, 用于前端可解释性展示.
    """
    score = 0
    hit_reasons: List[str] = []
    disputed = llm_disputed or {}

    style_name = style["name"]

    # 1. 标签基础分 — features[tag]==True → +2, 争议特征 → +1
    for tag in style.get("tags", []):
        if features.get(tag):
            zh = _FEAT_ZH.get(tag, tag)
            if disputed.get(tag):
                score += 1
                hit_reasons.append(f"特征匹配(LLM争议): {zh}")
            else:
                score += 2
                hit_reasons.append(f"特征匹配: {zh}")

    # 2. 学习权重分 — 三级阶梯映射 (值域 [0,1])
    #    w >= 0.7 → +2 (高: 历史强验证)
    #    w >= 0.4 → +1 (中: 历史中等验证)
    #    w <  0.4 →  0 (不足: 历史证据不充分)
    learning_bonus = 0
    learned_detail: List[str] = []
    if learned_weights:
        style_name = style["name"]
        for feat, is_active in features.items():
            if is_active and feat in learned_weights:
                w = learned_weights[feat].get(style_name, 0)
                feat_zh = _FEAT_ZH.get(feat, feat)
                if w >= 0.7:
                    score += 2
                    learning_bonus += 2
                    hit_reasons.append(f"学习权重(高): {feat_zh}→{style_name} (+2)")
                    learned_detail.append(feat_zh)
                elif w >= 0.4:
                    score += 1
                    learning_bonus += 1
                    hit_reasons.append(f"学习权重(中): {feat_zh}→{style_name} (+1)")
                    learned_detail.append(feat_zh)
                elif w <= -0.7:
                    score -= 2
                    learning_bonus -= 2
                    hit_reasons.append(f"学习权重(负高): {feat_zh}→{style_name} (-2)")
                    learned_detail.append(feat_zh)
                elif w <= -0.4:
                    score -= 1
                    learning_bonus -= 1
                    hit_reasons.append(f"学习权重(负中): {feat_zh}→{style_name} (-1)")
                    learned_detail.append(feat_zh)

    # 3. 7 条特定规则
    if style["name"] == "Event-Driven Architecture" and features.get("high_concurrency"):
        score += 1
        hit_reasons.append("特定规则: 高并发场景倾向事件驱动架构")
    if style["name"] == "Microservices" and features.get("team_size_large"):
        score += 1
        hit_reasons.append("特定规则: 多团队协作倾向微服务架构")
    if style["name"] == "Layered Architecture" and features.get("strict_consistency"):
        score += 1
        hit_reasons.append("特定规则: 强一致性需求适合分层架构")
    if style["name"] == "Pipeline-Filter" and features.get("data_intensive") and features.get("real_time"):
        score += 1
        hit_reasons.append("特定规则: 实时流处理倾向管道-过滤器架构")
    if style["name"] == "CQRS" and features.get("data_intensive") and features.get("high_concurrency"):
        score += 1
        hit_reasons.append("特定规则: 高并发数据访问倾向CQRS架构")
    if style["name"] == "Microservices" and features.get("high_concurrency") and features.get("strict_consistency"):
        score += 1
        hit_reasons.append("特定规则: 高并发+强一致性倾向微服务架构")

    # 4. 非对称惩罚 — 特定特征对某些风格是反向信号
    penalty_tags = style.get("penalty_tags", {})
    for feat, is_active in features.items():
        if is_active and feat in penalty_tags:
            penalty = penalty_tags[feat]
            score += penalty  # 负值累加, 最后统一夹底
            feat_zh = _FEAT_ZH.get(feat, feat)
            hit_reasons.append(f"反向信号: {feat_zh} ({penalty})")

    # 最终夹底: 得分不低于 0
    score = max(0, score)

    return {
        "style": style["name"],
        "style_zh": style.get("name_zh", style["name"]),
        "score": score,
        "reasons": hit_reasons,
        "learning_bonus": learning_bonus,
        "learned_detail": learned_detail,
        "pros": style.get("pros", []),
        "pros_zh": style.get("pros_zh", []),
        "cons": style.get("cons", []),
        "cons_zh": style.get("cons_zh", []),
        "best_for": style.get("best_for", []),
        "best_for_zh": style.get("best_for_zh", []),
        "topology_mermaid": style.get("topology_mermaid", ""),
    }


def select_top3(scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从全部评分结果中选择 Top 3 候选.
    策略: 主流优先 + 按分补齐 + 零分保底.
    """
    by_name = {item["style"]: item for item in scored}
    mainstream_ranked = [by_name[name] for name in MAINSTREAM_STYLES if name in by_name]
    non_mainstream = [item for item in scored if item["style"] not in MAINSTREAM_STYLES]

    if all(item["score"] == 0 for item in mainstream_ranked):
        return mainstream_ranked[:3]

    top3: List[Dict[str, Any]] = []
    for item in mainstream_ranked:
        if item["score"] > 0 and len(top3) < 3:
            top3.append(item)
    for item in sorted(scored, key=lambda x: x["score"], reverse=True):
        if item["score"] > 0 and item["style"] not in {x["style"] for x in top3} and len(top3) < 3:
            top3.append(item)
    if len(top3) < 3:
        for item in sorted(non_mainstream, key=lambda x: x["score"], reverse=True):
            if item["score"] > 0 and item["style"] not in {x["style"] for x in top3} and len(top3) < 3:
                top3.append(item)
    # 不足 3 个时用最高分候补补齐 (跳过负分, 同分按标签匹配数降序)
    if len(top3) < 3:
        remaining = sorted(
            [item for item in scored if item["style"] not in {x["style"] for x in top3}
             and item["score"] >= 0],
            key=lambda x: (x["score"],
                           len([r for r in x.get("reasons", [])
                                if "特征匹配" in r])),
            reverse=True
        )
        for item in remaining:
            if len(top3) >= 3:
                break
            top3.append(item)
    if len(top3) == 0:
        return mainstream_ranked[:3]
    return top3
