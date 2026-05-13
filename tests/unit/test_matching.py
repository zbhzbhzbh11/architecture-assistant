"""匹配模块单元测试: 规则引擎 + 图谱融合."""

import pytest
from services.matching_agent.app.main import score_style
from services.matching_agent.app.graph_matcher import blend_scores, fetch_graph_evidence


# ── 规则引擎评分测试 (保持原样) ──

def test_score_style_layered():
    style = {
        "name": "Layered Architecture",
        "tags": ["complex_business", "strict_consistency"]
    }
    features = {"complex_business": True, "strict_consistency": True}
    result = score_style(style, features)

    assert result["score"] == 5
    assert "matches feature: complex_business" in result["reasons"]
    assert "extra rule: strict consistency fits layered core domain" in result["reasons"]


def test_score_style_event_driven():
    style = {
        "name": "Event-Driven Architecture",
        "tags": ["high_concurrency", "real_time"]
    }
    features = {"high_concurrency": True, "real_time": True}
    result = score_style(style, features)

    assert result["score"] == 5
    assert "extra rule: high concurrency favors event-driven" in result["reasons"]


# ── 图谱融合测试 ──

def test_blend_scores_no_graph_evidence():
    """无图谱证据时, 规则评分不变但填充空图字段."""
    rule_scored = [
        {"style": "Layered Architecture", "score": 5, "reasons": ["matches feature: complex_business"]},
        {"style": "Microservices", "score": 3, "reasons": []},
    ]
    result = blend_scores(rule_scored, None)
    assert result[0]["score"] == 5  # 分数不变
    assert "graph_score" in result[0]
    assert result[0]["graph_score"] == 0
    assert "graph_reasons" in result[0]
    assert result[0]["graph_reasons"] == []
    assert "matched_attributes" in result[0]
    assert "matched_scenarios" in result[0]
    assert "related_risks" in result[0]
    assert "combinable_styles" in result[0]


def test_blend_scores_with_graph_evidence():
    """图谱证据应增加 graph_score 但不超过规则得分 50%."""
    rule_scored = [
        {"style": "Event-Driven Architecture", "score": 6, "reasons": ["matches: high_concurrency"]},
        {"style": "Microservices", "score": 4, "reasons": ["matches: scalability"]},
    ]
    graph_evidence = {
        "available": True,
        "active_features": ["high_concurrency", "real_time"],
        "ranked": [
            {
                "style": "Event-Driven Architecture",
                "graph_score": 6,
                "matched_attributes": ["high_concurrency", "real_time", "scalability"],
                "matched_scenarios": ["real-time messaging"],
                "related_risks": ["事件一致性设计难度大"],
                "combinable_styles": ["CQRS"],
            },
        ],
    }
    result = blend_scores(rule_scored, graph_evidence)

    eda = next(r for r in result if r["style"] == "Event-Driven Architecture")
    # 图谱加分: min(6, 6//2) = min(6, 3) = 3 → score = 6 + 3 = 9
    assert eda["score"] == 9
    assert eda["graph_score"] == 6
    assert "high_concurrency" in eda["matched_attributes"]
    assert "real-time messaging" in eda["matched_scenarios"]
    assert "事件一致性设计难度大" in eda["related_risks"]
    assert "CQRS" in eda["combinable_styles"]

    ms = next(r for r in result if r["style"] == "Microservices")
    assert ms["score"] == 4  # 无图谱证据, 保持原分
    assert ms["graph_score"] == 0


def test_blend_scores_empty_evidence():
    """graph_evidence 含空 ranked 时, 不改变分数."""
    rule_scored = [
        {"style": "Layered Architecture", "score": 5, "reasons": []},
    ]
    result = blend_scores(rule_scored, {"available": True, "ranked": []})
    assert result[0]["score"] == 5
    assert result[0]["graph_score"] == 0


def test_candidates_have_graph_fields():
    """验证 score_style 输出可以被 blend_scores 正常填充."""
    from services.matching_agent.app.main import score_style

    style = {
        "name": "Layered Architecture",
        "name_zh": "分层架构",
        "tags": ["complex_business", "strict_consistency"],
        "pros": ["high maintainability"],
        "pros_zh": ["可维护性高"],
        "cons": ["performance overhead"],
        "cons_zh": ["性能开销"],
        "best_for": ["enterprise app"],
        "best_for_zh": ["企业级应用"],
        "topology_mermaid": "graph LR\nA-->B",
    }
    features = {"complex_business": True, "strict_consistency": True}
    result = score_style(style, features)

    blended = blend_scores([result], None)
    assert blended[0]["style"] == "Layered Architecture"
    assert blended[0]["reasons"]
    assert "graph_score" in blended[0]
    assert "graph_reasons" in blended[0]


# ── 组合推荐测试 ──────────────────────────────────────────────

def test_score_combination_basic():
    """组合评分: 两个高分风格组合应得更高分."""
    from services.matching_agent.app.combo_matcher import score_combination

    combo = {
        "name": "Microservices + Event-Driven Architecture",
        "name_zh": "微服务 + 事件驱动",
        "styles": ["Microservices", "Event-Driven Architecture"],
        "tags": ["high_concurrency", "scalability"],
        "synergy": "Good combo",
        "synergy_zh": "好的组合",
        "complexity_penalty": 1,
    }
    scored = {
        "Microservices": {"style": "Microservices", "score": 6, "matched_attributes": ["high_concurrency"]},
        "Event-Driven Architecture": {"style": "Event-Driven Architecture", "score": 8, "matched_attributes": ["high_concurrency", "real_time"]},
    }
    features = {"high_concurrency": True, "real_time": True, "scalability": True}
    result = score_combination(combo, scored, features)

    assert result["combo_score"] > 0
    assert "component scores sum" in " ".join(result["reasons"])
    assert "complexity penalty" in " ".join(result["reasons"])
    assert result["component_details"]


def test_rank_combinations_top3():
    """rank_combinations 应返回不超过 3 个组合."""
    from services.matching_agent.app.combo_matcher import rank_combinations

    combos = [
        {"name": "A+B", "name_zh": "A+B", "styles": ["Layered Architecture", "CQRS"], "tags": ["complex_business"], "synergy": "x", "synergy_zh": "x", "complexity_penalty": 1},
        {"name": "C+D", "name_zh": "C+D", "styles": ["Microservices", "Event-Driven Architecture"], "tags": ["high_concurrency"], "synergy": "y", "synergy_zh": "y", "complexity_penalty": 1},
        {"name": "E+F", "name_zh": "E+F", "styles": ["Pipeline-Filter", "Event-Driven Architecture"], "tags": ["data_intensive"], "synergy": "z", "synergy_zh": "z", "complexity_penalty": 2},
        {"name": "G+H", "name_zh": "G+H", "styles": ["Hexagonal Architecture", "Microservices"], "tags": ["scalability"], "synergy": "w", "synergy_zh": "w", "complexity_penalty": 2},
    ]
    scored = {
        "Layered Architecture": {"style": "Layered Architecture", "score": 5},
        "CQRS": {"style": "CQRS", "score": 4},
        "Microservices": {"style": "Microservices", "score": 6},
        "Event-Driven Architecture": {"style": "Event-Driven Architecture", "score": 7},
        "Pipeline-Filter": {"style": "Pipeline-Filter", "score": 5},
        "Hexagonal Architecture": {"style": "Hexagonal Architecture", "score": 3},
    }
    features = {"high_concurrency": True}
    result = rank_combinations(combos, scored, features, top_n=3)
    assert len(result) <= 3
    assert all("combo_score" in r for r in result)


def test_combination_for_im_scenario():
    """即时通讯场景应出现 Microservices + Event-Driven 组合."""
    from services.matching_agent.app.combo_matcher import rank_combinations

    combos = [
        {"name": "Microservices + Event-Driven Architecture", "name_zh": "微服务+事件驱动", "styles": ["Microservices", "Event-Driven Architecture"], "tags": ["high_concurrency", "real_time"], "synergy": "x", "synergy_zh": "x", "complexity_penalty": 1},
        {"name": "Layered Architecture + CQRS", "name_zh": "分层+CQRS", "styles": ["Layered Architecture", "CQRS"], "tags": ["complex_business"], "synergy": "y", "synergy_zh": "y", "complexity_penalty": 1},
    ]
    scored = {
        "Microservices": {"style": "Microservices", "score": 6, "matched_attributes": ["high_concurrency"]},
        "Event-Driven Architecture": {"style": "Event-Driven Architecture", "score": 8, "matched_attributes": ["high_concurrency", "real_time"]},
        "Layered Architecture": {"style": "Layered Architecture", "score": 3, "matched_attributes": []},
        "CQRS": {"style": "CQRS", "score": 4, "matched_attributes": []},
    }
    features = {"high_concurrency": True, "real_time": True}
    result = rank_combinations(combos, scored, features, top_n=3)
    # 微服务+事件驱动 应该排第一 (高分 + 高并发+实时特征覆盖)
    assert "Microservices" in result[0]["combination_name"]
