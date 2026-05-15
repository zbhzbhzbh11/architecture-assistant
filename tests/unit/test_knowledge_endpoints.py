"""知识库端点集成测试 — 直接调用 handler 函数 (FastAPI 无副作用).

覆盖:
  - GET /styles → 10 种风格, 结构验证
  - POST /styles → 新增 + 验证写入
  - POST /feedback → 反馈收集 + learned_weights 更新
  - GET /adr → ADR 列表格式验证
  - _repo() 调度器三分支: json / neo4j / auto
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# ── sys.modules mock (必须放在 import services 之前) ──
for _mod in ('httpx', 'fastapi', 'fastapi.middleware', 'fastapi.middleware.cors'):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
# httpx 的 HTTPStatusError 需为真实 Exception 子类
_hm = sys.modules['httpx']
_hm.HTTPStatusError = type('HTTPStatusError', (Exception,), {})
_hm.AsyncClient = MagicMock()
_hm.Response = MagicMock()

import pytest

_SR = Path(__file__).resolve().parent.parent.parent
if str(_SR) not in sys.path:
    sys.path.insert(0, str(_SR))

from services.knowledge_base.app.main import (
    app, get_styles, add_style_endpoint, add_feedback_endpoint,
    feedback_stats, get_learned_weights, list_adrs,
    StylePayload, FeedbackPayload,
    _repo, BACKEND,
)
from services.knowledge_base.app.main import _prefer_graph, _require_graph
from services.knowledge_base.app.json_repository import JsonRepository
from services.knowledge_base.app.graph_repository import GraphRepository


# ====================================================================
# 端点测试
# ====================================================================

class TestGetStylesEndpoint:
    """GET /styles 端点."""

    def test_returns_10_styles(self):
        result = get_styles()
        styles = result["styles"]
        assert len(styles) >= 10, f"应返回 >= 10 种风格, 实得 {len(styles)}"

    def test_each_style_has_required_fields(self):
        data = get_styles()
        required = {"name", "tags", "best_for", "pros", "cons"}
        for style in data["styles"]:
            missing = required - set(style.keys()) - {"name_zh", "pros_zh", "cons_zh", "best_for_zh", "topology_mermaid"}
            assert len(missing) == 0, f"{style.get('name','?')}: 缺少必填字段 {missing}"

    def test_contains_mainstream_three(self):
        data = get_styles()
        names = {s["name"] for s in data["styles"]}
        mainstream = ["Layered Architecture", "Microservices", "Event-Driven Architecture"]
        for m in mainstream:
            assert m in names, f"缺少主流风格: {m}"

    def test_each_style_has_topology_mermaid(self):
        data = get_styles()
        for style in data["styles"]:
            assert style.get("topology_mermaid"), f"{style.get('name','?')}: 缺少 topology_mermaid"


class TestAddStyleEndpoint:
    """POST /styles 端点."""

    def test_add_and_verify(self):
        before = get_styles()
        count_before = len(before["styles"])

        payload = StylePayload(
            name="TestNewStyle",
            tags=["scalability", "real_time"],
            best_for=["testing"],
            pros=["fast", "easy"],
            cons=["limited scope"],
        )
        result = add_style_endpoint(payload)
        assert result["status"] == "ok"
        assert result["count"] >= count_before + 1

        # 验证写入
        after = get_styles()
        names = [s["name"] for s in after["styles"]]
        assert "TestNewStyle" in names

        # 清理
        from services.knowledge_base.app.main import save_styles
        after["styles"] = [s for s in after["styles"] if s["name"] != "TestNewStyle"]
        save_styles(after)


class TestFeedbackEndpoint:
    """POST /feedback + POST /feedback/stats + GET /feedback/weights 端点."""

    def test_feedback_flow(self):
        payload = FeedbackPayload(
            requirement="测试端点需求",
            recommended_style="Microservices",
            user_choice="Event-Driven Architecture",
            comment="端点测试用户选择了事件驱动",
        )
        result = add_feedback_endpoint(payload)
        assert result.get("status") == "ok"

        stats = feedback_stats()
        assert stats["total"] >= 1

        weights = get_learned_weights()
        assert "weights" in weights
        assert "total_feedback_learned" in weights

        # 清理
        from services.knowledge_base.app.main import FEEDBACK_PATH
        import json as _json
        if FEEDBACK_PATH.exists():
            fb = _json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
            fb = [e for e in fb if e.get("comment") != "端点测试用户选择了事件驱动"]
            FEEDBACK_PATH.write_text(_json.dumps(fb, ensure_ascii=False, indent=2), encoding="utf-8")


class TestADREndpoint:
    """GET /adr 端点."""

    def test_list_adrs_returns_dict(self):
        result = list_adrs(limit=10)
        assert "adrs" in result
        assert "total" in result
        assert isinstance(result["adrs"], list)

    def test_adr_item_structure(self):
        result = list_adrs(limit=10)
        if result["total"] > 0:
            adr = result["adrs"][0]
            assert "adr_id" in adr
            assert "requirement" in adr
            assert "recommended_style" in adr
            assert "timestamp" in adr


# ====================================================================
# _repo() 调度器三分支测试
# ====================================================================

class TestRepoScheduler:
    """_repo() 调度器: json / neo4j / auto 三个 BACKEND 分支."""

    def test_json_backend_routes_to_json(self):
        """BACKEND=json → _prefer_graph()=False → 直接走 JsonRepository."""
        with patch.object(sys.modules['services.knowledge_base.app.main'], 'BACKEND', 'json'):
            assert _prefer_graph() is False
            assert _require_graph() is False
            result = _repo("get_styles")
            assert "styles" in result
            assert len(result["styles"]) >= 10

    def test_auto_backend_with_neo4j_unavailable_falls_back(self):
        """BACKEND=auto + Neo4j 不可用 → 先尝试 Graph → 返回 None → fallback JSON."""
        with patch.object(sys.modules['services.knowledge_base.app.main'], 'BACKEND', 'auto'), \
             patch.object(GraphRepository, 'get_styles', return_value=None):
            assert _prefer_graph() is True
            assert _require_graph() is False
            result = _repo("get_styles")
            assert result is not None
            assert "styles" in result
            assert len(result["styles"]) >= 10

    def test_neo4j_backend_raises_when_unavailable(self):
        """BACKEND=neo4j + Neo4j 不可用 → RuntimeError."""
        with patch.object(sys.modules['services.knowledge_base.app.main'], 'BACKEND', 'neo4j'), \
             patch.object(GraphRepository, 'get_styles', return_value=None):
            assert _prefer_graph() is True
            assert _require_graph() is True
            with pytest.raises(RuntimeError, match="Neo4j is required"):
                _repo("get_styles")

    def test_prefer_graph_returns_graph_result_when_available(self):
        """BACKEND=auto + Neo4j 可用 → 返回 GraphRepository 结果."""
        with patch.object(sys.modules['services.knowledge_base.app.main'], 'BACKEND', 'auto'), \
             patch.object(GraphRepository, 'get_styles', return_value={"styles": [{"name": "FromGraph"}]}):
            result = _repo("get_styles")
            assert result == {"styles": [{"name": "FromGraph"}]}
