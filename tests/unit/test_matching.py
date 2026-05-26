"""匹配模块单元测试: 规则引擎 + 图谱融合."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVICES_ROOT = _PROJECT_ROOT / "services"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

# ── Mock missing modules before importing services ──
if 'httpx' not in sys.modules:
    _httpx_mock = MagicMock()
    _httpx_mock.HTTPStatusError = type('HTTPStatusError', (Exception,), {})
    _httpx_mock.AsyncClient = MagicMock()
    _httpx_mock.Response = MagicMock()
    sys.modules['httpx'] = _httpx_mock
for _mod in ('fastapi', 'fastapi.middleware', 'fastapi.middleware.cors'):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest

try:
    import langgraph  # noqa: F401
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

_needs_langgraph = pytest.mark.skipif(not _LANGGRAPH_AVAILABLE, reason="langgraph not installed")

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
    assert "特征匹配: 复杂业务" in result["reasons"]
    assert "特定规则: 强一致性需求适合分层架构" in result["reasons"]


def test_score_style_event_driven():
    style = {
        "name": "Event-Driven Architecture",
        "tags": ["high_concurrency", "real_time"]
    }
    features = {"high_concurrency": True, "real_time": True}
    result = score_style(style, features)

    assert result["score"] == 5
    assert "特定规则: 高并发场景倾向事件驱动架构" in result["reasons"]


# ── 图谱融合测试 ──

def test_blend_scores_no_graph_evidence():
    """无图谱证据时, 规则评分不变但填充空图字段."""
    rule_scored = [
        {"style": "Layered Architecture", "score": 5, "reasons": ["特征匹配: 复杂业务"]},
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


# ── learned_weights 累计加分 ────────────────────────────────────

def test_learned_weights_boosts_score():
    """归一化权重 >= 0.5 (strong) -> 分数 +1 (含 learned boost 理由)."""
    style = {
        "name": "Event-Driven Architecture",
        "name_zh": "事件驱动架构",
        "tags": ["high_concurrency", "real_time"],
        "pros": ["high throughput"],
        "pros_zh": ["高吞吐量"],
        "cons": ["hard tracing"],
        "cons_zh": ["调试困难"],
        "best_for": ["real-time messaging"],
        "best_for_zh": ["实时消息系统"],
        "topology_mermaid": "",
    }
    features = {"high_concurrency": True, "real_time": True, "scalability": True}
    learned_weights = {
        "scalability": {"Event-Driven Architecture": 0.8},
    }

    no_weight = score_style(style, features)
    with_weight = score_style(style, features, learned_weights)

    assert with_weight["score"] == no_weight["score"] + 1, \
        f"强权重应 +1: 无权={no_weight['score']}, 有权={with_weight['score']}"
    assert any("学习权重(强)" in r for r in with_weight["reasons"]), \
        f"理由应含 学习权重(强): {with_weight['reasons']}"
    assert "可扩展性" in " ".join(with_weight["reasons"])


def test_learned_weights_below_threshold_no_effect():
    """归一化权重 < 0.3 → 阈值未达, 不影响分数."""
    style = {
        "name": "Event-Driven Architecture",
        "name_zh": "事件驱动架构",
        "tags": ["high_concurrency"],
        "pros": ["high throughput"],
        "pros_zh": ["高吞吐量"],
        "cons": ["hard tracing"],
        "cons_zh": ["调试困难"],
        "best_for": ["real-time messaging"],
        "best_for_zh": ["实时消息系统"],
        "topology_mermaid": "",
    }
    features = {"high_concurrency": True, "real_time": True}
    # 归一化值: 0.25 < 0.3 阈值 → 不生效
    learned_weights = {
        "real_time": {"Event-Driven Architecture": 0.25},
    }

    no_weight = score_style(style, features)
    with_weight = score_style(style, features, learned_weights)

    assert with_weight["score"] == no_weight["score"], \
        f"归一化权 <0.3 不应加分: 无权={no_weight['score']}, 有权={with_weight['score']}"
    assert not any("学习权重" in r for r in with_weight["reasons"])


# ── top3 边界补齐测试 ───────────────────────────────────────────

@_needs_langgraph
@pytest.mark.skip(reason="needs knowledge-base Docker service running")
def test_top3_zero_score_returns_mainstream():
    """全部特征未命中(全 0 分) → 仍返回 3 个候选且主流架构必在列."""
    import asyncio
    from services.matching_agent.app.main import match, MatchRequest
    from services.knowledge_base.app.main import load_styles

    kb_data = load_styles()
    features = {}

    with patch("httpx.AsyncClient") as mock_client, \
         patch("services.matching_agent.app.main.fetch_graph_evidence", new=AsyncMock(return_value=None)):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = kb_data
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value.get.return_value = mock_resp
        mock_instance.__aenter__.return_value.post.return_value = mock_resp
        mock_client.return_value = mock_instance

        result = asyncio.run(match(MatchRequest(features=features)))

    assert len(result.candidates) >= 3, f"全 0 分应返回 ≥ 3 个候选: {len(result.candidates)}"
    mainstream = {"Layered Architecture", "Microservices", "Event-Driven Architecture"}
    candidate_names = {c["style"] for c in result.candidates}
    overlap = candidate_names & mainstream
    assert len(overlap) >= 1, f"候选未含主流架构: {candidate_names}"


@_needs_langgraph
@pytest.mark.skip(reason="needs knowledge-base Docker service running")
def test_top3_non_mainstream_lead_still_includes_mainstream():
    """非主流架构评分更高时 → 主流架构仍应出现在候选集中."""
    import asyncio
    from services.matching_agent.app.main import match, MatchRequest

    features = {"deployment_constraint": True}

    with patch("httpx.AsyncClient") as mock_client, \
         patch("services.matching_agent.app.main.fetch_graph_evidence", new=AsyncMock(return_value=None)):
        from services.knowledge_base.app.main import load_styles
        kb_data = load_styles()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = kb_data
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value.get.return_value = mock_resp
        mock_instance.__aenter__.return_value.post.return_value = mock_resp
        mock_client.return_value = mock_instance

        result = asyncio.run(match(MatchRequest(features=features)))

    assert len(result.candidates) >= 3, f"应返回 ≥ 3 个候选: {len(result.candidates)}"
    mainstream = {"Layered Architecture", "Microservices", "Event-Driven Architecture"}
    candidate_names = {c["style"] for c in result.candidates}
    overlap = candidate_names & mainstream
    assert len(overlap) >= 1, f"候选未含主流架构: {candidate_names}"
