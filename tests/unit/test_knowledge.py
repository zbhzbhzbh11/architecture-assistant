"""知识库模块单元测试.

覆盖:
  - JSON 文件存储 (fallback 路径)
  - Neo4j 图存储 (可选, Neo4j 不可用时自动跳过)
  - /graph/status 端点
  - 后端切换逻辑
"""

import os
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.knowledge_base.app.main import (
    load_styles, add_style, add_feedback, get_feedback_stats,
    StylePayload, FeedbackPayload, save_styles, FEEDBACK_PATH,
)
from services.knowledge_base.app.json_repository import JsonRepository
from services.knowledge_base.app.graph_repository import GraphRepository
from services.knowledge_base.app.main import ADRPayload


# ── 辅助: 检测 Neo4j 是否可用 ──────────────────────────────────

def _neo4j_available() -> bool:
    """检测 Neo4j 是否可达."""
    try:
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


NEO4J_SKIP_REASON = "Neo4j not available"
neo4j_required = pytest.mark.skipif(not _neo4j_available(), reason=NEO4J_SKIP_REASON)


# ── JSON 存储测试 (始终运行) ───────────────────────────────────

class TestKnowledgeBaseLoad:
    """知识库加载与数据完整性测试 (JSON fallback)."""

    def test_styles_count_at_least_10(self):
        data = load_styles()
        styles = data["styles"]
        assert len(styles) >= 10, f"架构风格数量不足: {len(styles)} < 10"

    def test_each_style_has_required_fields(self):
        data = load_styles()
        required = {"name", "tags", "best_for", "pros", "cons"}
        for style in data["styles"]:
            missing = required - set(style.keys())
            name = style.get("name", "?")
            assert not missing, f"{name}: 缺少字段 {missing}"

    def test_contains_mainstream_styles(self):
        data = load_styles()
        names = {s["name"] for s in data["styles"]}
        mainstream = [
            "Layered Architecture",
            "Microservices",
            "Event-Driven Architecture",
        ]
        missing = [m for m in mainstream if m not in names]
        assert not missing, f"缺少主流架构: {missing}"

    def test_topo_mermaid_not_empty(self):
        data = load_styles()
        for style in data["styles"]:
            topo = style.get("topology_mermaid", "")
            name = style.get("name", "?")
            assert topo, f"{name}: 缺少 topology_mermaid"

    def test_pros_cons_non_empty(self):
        data = load_styles()
        for style in data["styles"]:
            name = style.get("name", "?")
            assert len(style.get("pros", [])) > 0, f"{name}: pros 为空"
            assert len(style.get("cons", [])) > 0, f"{name}: cons 为空"


class TestKnowledgeExtension:
    """知识库扩展接口测试 (JSON)."""

    def test_add_style(self):
        before = load_styles()
        count_before = len(before["styles"])

        payload = StylePayload(
            name="Test Style",
            tags=["scalability"],
            best_for=["testing"],
            pros=["easy to test"],
            cons=["not real"],
        )
        result = add_style(payload)
        assert result["status"] == "ok"

        after = load_styles()
        count_after = len(after["styles"])
        assert count_after == count_before + 1

        # 清理
        after["styles"] = [s for s in after["styles"] if s["name"] != "Test Style"]
        save_styles(after)


class TestFeedback:
    """案例学习反馈接口测试 (JSON)."""

    def test_add_and_stats(self):
        payload = FeedbackPayload(
            requirement="测试需求",
            recommended_style="Layered Architecture",
            user_choice="Microservices",
            comment="测试反馈",
        )
        result = add_feedback(payload)
        assert result["status"] == "ok"

        stats = get_feedback_stats()
        assert stats["total"] >= 1

        # 清理
        if FEEDBACK_PATH.exists():
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                fb = json.load(f)
            fb = [e for e in fb if e.get("comment") != "测试反馈"]
            with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
                json.dump(fb, f, ensure_ascii=False, indent=2)


# ── JSON Repository 直接测试 ───────────────────────────────────

class TestJsonRepository:
    """直接测试 JsonRepository 方法."""

    def test_get_styles_returns_dict(self):
        result = JsonRepository.get_styles()
        assert "styles" in result
        assert isinstance(result["styles"], list)
        assert len(result["styles"]) >= 10

    def test_graph_status_json(self):
        status = JsonRepository.graph_status()
        assert status["backend"] == "json"
        assert status["neo4j_available"] is False
        assert status["node_count"] >= 10

    def test_get_feedback(self):
        result = JsonRepository.get_feedback()
        assert "feedback" in result
        assert isinstance(result["feedback"], list)

    def test_get_learned_weights(self):
        result = JsonRepository.get_learned_weights()
        assert "weights" in result
        assert "total_feedback_learned" in result


# ── Graph Status 端点测试 (始终运行, 不依赖 Neo4j) ─────────────

class TestGraphStatusEndpoint:
    """测试 /graph/status 端点 (使用默认 JSON backend)."""

    def test_graph_status_returns_backend_field(self):
        status = JsonRepository.graph_status()
        assert "backend" in status
        assert status["backend"] in ("json", "neo4j")
        assert "neo4j_available" in status
        assert "node_count" in status

    def test_json_fallback_is_always_available(self):
        """验证 JSON fallback 在任何情况下都可用."""
        result = load_styles()
        assert "styles" in result
        assert len(result["styles"]) >= 10


# ── Neo4j 图存储测试 (仅 Neo4j 可用时运行) ─────────────────────

@pytest.mark.integration
class TestGraphRepository:
    """Neo4j 图存储测试 — 仅当 Neo4j 可用时运行."""

    @neo4j_required
    def test_graph_status_neo4j(self):
        status = GraphRepository.graph_status()
        assert status["neo4j_available"] is True
        assert status["backend"] == "neo4j"

    @neo4j_required
    def test_get_styles_from_neo4j(self):
        result = GraphRepository.get_styles()
        assert result is not None
        assert "styles" in result
        assert len(result["styles"]) >= 1

    @neo4j_required
    def test_graph_status_has_counts(self):
        status = GraphRepository.graph_status()
        if status["neo4j_available"]:
            assert status["node_count"] >= 1
            assert "relationship_count" in status


# ── ADR 存储与查询测试 ────────────────────────────────────────

class TestADR:
    """ADR (Architecture Decision Record) 存储和查询测试."""

    def test_create_adr(self):
        """POST /adr 应返回 adr_id 和 status."""
        payload = ADRPayload(
            requirement="测试需求：高并发实时消息系统",
            extracted_features={"high_concurrency": True, "real_time": True},
            candidates=[
                {"style": "Event-Driven Architecture", "score": 8},
                {"style": "Microservices", "score": 5},
            ],
            recommended_style="Event-Driven Architecture",
            recommended_style_zh="事件驱动架构",
            alternative_styles=["Microservices"],
            decision_basis={"rule_engine": ["高并发场景处理能力强"], "llm_summary": "推荐事件驱动..."},
            risk_and_suggestions={"main_risks": ["复杂度高"], "suggestions": ["引入消息队列"]},
        )
        result = JsonRepository.add_adr(payload.model_dump())
        assert result["status"] == "ok"
        assert "adr_id" in result
        assert result["adr_id"].startswith("ADR-")
        assert result["total"] >= 1

    def test_list_adrs(self):
        """GET /adr 应返回列表."""
        result = JsonRepository.get_adrs(limit=10)
        assert "adrs" in result
        assert "total" in result
        assert result["total"] >= 1

    def test_get_adr_by_id(self):
        """GET /adr/{id} 应返回对应 ADR."""
        list_result = JsonRepository.get_adrs(limit=50)
        if list_result["total"] > 0:
            adr_id = list_result["adrs"][-1]["adr_id"]
            adr = JsonRepository.get_adr(adr_id)
            assert adr is not None
            assert adr["adr_id"] == adr_id
            assert "recommended_style" in adr

    def test_adr_contains_required_fields(self):
        """ADR 应包含必填字段: requirement, features, candidates, recommended_style, timestamp."""
        list_result = JsonRepository.get_adrs(limit=50)
        if list_result["total"] > 0:
            adr = list_result["adrs"][-1]
            assert "requirement" in adr
            assert "extracted_features" in adr
            assert "candidates" in adr
            assert "recommended_style" in adr
            assert "decision_basis" in adr
            assert "timestamp" in adr
            assert "risk_and_suggestions" in adr

    def test_adr_style_consistency(self):
        """ADR 中 recommended_style 应与原始记录一致."""
        list_result = JsonRepository.get_adrs(limit=50)
        if list_result["total"] > 0:
            adr = list_result["adrs"][-1]
            assert adr["recommended_style"] == "Event-Driven Architecture"

    def test_get_nonexistent_adr(self):
        """不存在的 ADR 应返回 None."""
        result = JsonRepository.get_adr("ADR-nonexistent-999")
        assert result is None
