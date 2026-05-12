"""评估模块单元测试：核心逻辑函数（不依赖 HTTP 服务）."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


REQUIREMENT_TEXT = (
    "开发一个跨平台的即时通讯系统，要求支持万人同时在线，"
    "需要保证消息的实时性和可靠性，后期可能需要快速扩展视频通话功能"
)


# ————————————————————————————————————————————
# 需求分析：直接调 extract（纯计算，无 HTTP）
# ————————————————————————————————————————————

def test_extract_features():
    """[需求分析] 应提取出高并发、实时性、可靠性、可扩展性特征."""
    import asyncio
    from services.requirements_agent.app.main import extract, ExtractRequest

    result = asyncio.run(extract(ExtractRequest(requirement=REQUIREMENT_TEXT)))

    features = result.features
    assert features["high_concurrency"] is True, "应识别到高并发特征"
    assert features["real_time"] is True, "应识别到实时性特征"
    assert features["reliability"] is True, "应识别到可靠性特征"
    assert features["scalability"] is True, "应识别到可扩展性特征"

    hits = result.feature_hits
    assert len(hits["high_concurrency"]) > 0, "高并发应有命中关键词"
    assert len(hits["real_time"]) > 0, "实时性应有命中关键词"


def test_extract_security():
    """[需求分析] 安全特征应被正确提取."""
    import asyncio
    from services.requirements_agent.app.main import extract, ExtractRequest

    result = asyncio.run(extract(ExtractRequest(
        requirement="政务系统需要安全隔离、审计和权限控制。"
    )))
    assert result.features["security"] is True, "应识别到安全性特征"
    assert any("安全" in h or "审计" in h or "权限" in h for h in result.feature_hits["security"])


# ————————————————————————————————————————————
# 架构匹配：直接调 score_style + 用 Mock 调 match
# ————————————————————————————————————————————

def test_score_style_event_driven():
    """[规则引擎] Event-Driven 在高并发+实时性场景应得高分."""
    from services.matching_agent.app.main import score_style

    style = {
        "name": "Event-Driven Architecture",
        "tags": ["high_concurrency", "real_time", "scalability", "data_intensive"],
        "pros": ["high throughput", "loose coupling"],
        "cons": ["hard tracing", "eventual consistency complexity"],
    }
    features = {
        "high_concurrency": True,
        "real_time": True,
        "reliability": True,
        "scalability": True,
    }
    result = score_style(style, features)
    # tags: high_concurrency(2) + real_time(2) + scalability(2) = 6
    # extra: high concurrency favors event-driven = +1 = 7
    assert result["score"] >= 4, f"Event-Driven 应获高分, 实际 {result['score']}"
    assert len(result["reasons"]) >= 2, f"应有至少2条理由, 实际 {len(result['reasons'])}"
    assert len(result["pros"]) > 0
    assert len(result["cons"]) > 0


def test_score_style_layered():
    """[规则引擎] Layered 在强一致+复杂业务场景应获高分."""
    from services.matching_agent.app.main import score_style

    style = {
        "name": "Layered Architecture",
        "tags": ["complex_business", "strict_consistency"],
        "pros": ["high maintainability", "clear responsibility boundaries"],
        "cons": ["performance overhead", "slower cross-layer changes"],
    }
    features = {
        "complex_business": True,
        "strict_consistency": True,
    }
    result = score_style(style, features)
    # tags: 2+2 = 4, extra: strict_consistency fits layered = +1 = 5
    assert result["score"] >= 3, f"Layered 应获高分, 实际 {result['score']}"
    assert "extra rule: strict consistency fits layered core domain" in result["reasons"]


def test_match_candidates_count():
    """[架构推荐] Mock HTTP 后应返回至少 3 个候选架构."""
    import asyncio
    from services.matching_agent.app.main import match, MatchRequest
    from services.knowledge_base.app.main import load_styles

    kb_data = load_styles()
    features = {
        "high_concurrency": True, "real_time": True,
        "reliability": True, "scalability": True,
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = kb_data
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value.get.return_value = mock_resp
        mock_client.return_value = mock_instance

        result = asyncio.run(match(MatchRequest(features=features)))

    assert len(result.candidates) >= 3, f"候选架构数量不足: {len(result.candidates)} < 3"


def test_match_contains_mainstream():
    """[架构推荐] 候选架构应包含至少一种主流架构."""
    import asyncio
    from services.matching_agent.app.main import match, MatchRequest
    from services.knowledge_base.app.main import load_styles

    kb_data = load_styles()
    features = {"high_concurrency": True, "real_time": True}

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = kb_data
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value.get.return_value = mock_resp
        mock_client.return_value = mock_instance

        result = asyncio.run(match(MatchRequest(features=features)))

    mainstream = {"Layered Architecture", "Microservices", "Event-Driven Architecture"}
    candidate_names = {c["style"] for c in result.candidates}
    overlap = candidate_names & mainstream
    assert len(overlap) >= 1, f"候选集未包含主流架构: {candidate_names}"


def test_evaluate_returns_final_recommendation():
    """[决策评估] Mock HTTP 后应返回最终推荐、理由、优缺点、评分."""
    import asyncio
    from services.evaluation_agent.app.main import evaluate, EvaluateRequest
    from services.knowledge_base.app.main import load_styles
    from services.matching_agent.app.main import score_style

    kb_data = load_styles()
    features = {
        "high_concurrency": True, "real_time": True,
        "reliability": True, "scalability": True,
    }
    # 构建候选
    scored = [score_style(s, features) for s in kb_data["styles"]]
    scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = scored[:3]

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "推荐采用事件驱动架构..."}}]
        }
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value.post.return_value = mock_resp
        mock_client.return_value = mock_instance

        eval_result = asyncio.run(evaluate(EvaluateRequest(
            requirement=REQUIREMENT_TEXT,
            features=features,
            candidates=candidates,
        )))

    # 1. 必须有最终推荐
    assert eval_result["recommended_style"] is not None, "缺少最终推荐架构"
    assert len(eval_result["recommended_style"]) > 0

    # 2. 必须有备选架构
    assert len(eval_result.get("alternative_styles", [])) >= 1

    # 3. 必须有对比矩阵
    matrix = eval_result["comparison_matrix"]
    assert len(matrix) >= 3, f"对比矩阵应 >= 3 行, 实际 {len(matrix)}"

    # 4. 每行必须包含必填字段
    for row in matrix:
        assert "style" in row, f"矩阵行缺少 style: {row}"
        assert "score" in row, f"矩阵行缺少 score"
        assert "pros" in row, f"{row['style']}: 缺少 pros"
        assert "cons" in row, f"{row['style']}: 缺少 cons"
        assert "key_reasons" in row, f"{row['style']}: 缺少 key_reasons"
        assert isinstance(row["score"], int), f"{row['style']}: score 应为 int"

    # 5. 决策依据
    basis = eval_result["decision_basis"]
    assert "rule_engine" in basis, "缺少 rule_engine"
    assert "llm_summary" in basis, "缺少 llm_summary"
    assert len(basis.get("llm_summary", "")) > 0, "llm_summary 不应为空"

    # 6. 风险与建议
    risks = eval_result["risk_and_suggestions"]
    assert "main_risks" in risks
    assert "suggestions" in risks
    assert len(risks["main_risks"]) > 0
    assert len(risks["suggestions"]) > 0


def test_score_style_event_driven():
    """[规则引擎] Event-Driven 在高并发+实时性场景应得高分."""
    from services.matching_agent.app.main import score_style

    style = {
        "name": "Event-Driven Architecture",
        "tags": ["high_concurrency", "real_time", "scalability", "data_intensive"],
        "pros": ["high throughput", "loose coupling"],
        "cons": ["hard tracing", "eventual consistency complexity"],
    }
    features = {
        "high_concurrency": True,
        "real_time": True,
        "reliability": True,
        "scalability": True,
    }
    result = score_style(style, features)
    # tags: high_concurrency(2) + real_time(2) + scalability(2) = 6
    # extra: high concurrency favors event-driven = +1 = 7
    assert result["score"] >= 4, f"Event-Driven 应获高分, 实际 {result['score']}"
    assert len(result["reasons"]) >= 2, f"应有至少2条理由, 实际 {len(result['reasons'])}"
    assert len(result["pros"]) > 0
    assert len(result["cons"]) > 0


def test_score_style_layered():
    """[规则引擎] Layered 在强一致+复杂业务场景应获高分."""
    from services.matching_agent.app.main import score_style

    style = {
        "name": "Layered Architecture",
        "tags": ["complex_business", "strict_consistency"],
        "pros": ["high maintainability", "clear responsibility boundaries"],
        "cons": ["performance overhead", "slower cross-layer changes"],
    }
    features = {
        "complex_business": True,
        "strict_consistency": True,
    }
    result = score_style(style, features)
    # tags: 2+2 = 4, extra: strict_consistency fits layered = +1 = 5
    assert result["score"] >= 3, f"Layered 应获高分, 实际 {result['score']}"
    assert "extra rule: strict consistency fits layered core domain" in result["reasons"]


def test_localize_reasons():
    """[_localize_reasons] 英文规则理由应转为中文."""
    from services.evaluation_agent.app.main import _localize_reasons

    raw = [
        "matches feature: high_concurrency",
        "extra rule: high concurrency favors event-driven",
        "unknown_reason_xyz",
    ]
    result = _localize_reasons(raw)
    assert "高并发场景处理能力强" in result
    # 未知理由保留原文
    assert "unknown_reason_xyz" in result


def test_dynamic_risks_known_style():
    """[_dynamic_risks] 已知风格应返回针对性风险."""
    from services.evaluation_agent.app.main import _dynamic_risks

    risks = _dynamic_risks("Event-Driven Architecture", [])
    assert "main_risks" in risks
    assert "suggestions" in risks
    assert any("事件" in r for r in risks["main_risks"]), "事件驱动应有针对性风险描述"
    assert any("Kafka" in s or "消息队列" in s for s in risks["suggestions"])


def test_dynamic_risks_unknown_style():
    """[_dynamic_risks] 未知风格应返回通用风险."""
    from services.evaluation_agent.app.main import _dynamic_risks

    risks = _dynamic_risks("Unknown Style XYZ", [])
    assert len(risks["main_risks"]) > 0
    assert len(risks["suggestions"]) > 0
