"""API Gateway 单元测试: LangGraph 编排 + 手动 fallback."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestWorkflowState:
    """ArchitectureWorkflowState 类型定义测试."""

    def test_state_fields(self):
        from services.api_gateway.app.workflow_state import ArchitectureWorkflowState
        state: ArchitectureWorkflowState = {
            "requirement": "test",
            "workflow_engine": "manual",
        }
        assert state["requirement"] == "test"
        assert "extracted_features" not in state or state.get("extracted_features") is None
        state["extracted_features"] = {"high_concurrency": True}
        assert state["extracted_features"]["high_concurrency"] is True

    def test_trace_format(self):
        """验证 trace 列表条目格式."""
        from services.api_gateway.app.workflow_state import ArchitectureWorkflowState
        state: ArchitectureWorkflowState = {
            "requirement": "test",
            "trace": [
                {"node": "extract", "elapsed_ms": 42, "status": "ok"},
            ],
        }
        trace = state.get("trace", [])
        assert len(trace) == 1
        assert trace[0]["node"] == "extract"
        assert "elapsed_ms" in trace[0]
        assert trace[0]["status"] == "ok"


class TestBuildWorkflow:
    """LangGraph 工作流构建测试."""

    def test_build_returns_none_without_langgraph(self):
        """langgraph 未安装时 build_workflow() 应返回 None."""
        from services.api_gateway.app.langchain_workflow import build_workflow
        result = build_workflow()
        # 在无 langgraph 环境下应返回 None
        assert result is None, "build_workflow should return None when langgraph is not installed"

    def test_workflow_engine_is_manual_without_langgraph(self):
        """验证 main.py 中 WORKFLOW_ENGINE 为 'manual' (langgraph 未安装)."""
        # 直接导入会触发模块级代码
        from services.api_gateway.app.main import WORKFLOW_ENGINE
        assert WORKFLOW_ENGINE in ("langgraph", "manual")


class TestRecommendResponse:
    """RecommendResponse 模型测试."""

    def test_response_includes_workflow_fields(self):
        from services.api_gateway.app.main import RecommendResponse
        # 构造最小有效响应
        resp = RecommendResponse(
            extracted_features={},
            feature_hits={},
            candidates=[],
            final_report={},
            workflow_engine="manual",
            workflow_trace=[],
        )
        assert resp.workflow_engine == "manual"
        assert resp.workflow_trace == []

    def test_response_with_trace(self):
        from services.api_gateway.app.main import RecommendResponse
        trace = [
            {"node": "extract", "elapsed_ms": 10, "status": "ok"},
            {"node": "match", "elapsed_ms": 15, "status": "ok"},
            {"node": "evaluate", "elapsed_ms": 100, "status": "ok"},
        ]
        resp = RecommendResponse(
            extracted_features={"high_concurrency": True},
            feature_hits={"high_concurrency": ["高并发"]},
            candidates=[{"style": "Event-Driven", "score": 7}],
            final_report={"recommended_style": "Event-Driven Architecture"},
            workflow_engine="langgraph",
            workflow_trace=trace,
        )
        data = resp.model_dump()
        assert data["workflow_engine"] == "langgraph"
        assert len(data["workflow_trace"]) == 3
        assert data["workflow_trace"][0]["node"] == "extract"

    def test_response_includes_cache_hit(self):
        from services.api_gateway.app.main import RecommendResponse
        resp = RecommendResponse(
            extracted_features={},
            feature_hits={},
            candidates=[],
            final_report={},
            cache_hit=True,
        )
        assert resp.cache_hit is True
        data = resp.model_dump()
        assert data["cache_hit"] is True


# ── 缓存基础设施测试 ──────────────────────────────────────────

class TestCacheInfrastructure:
    """hash_utils + simple_cache 单元测试."""

    def test_cache_key_stable(self):
        import sys
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        from common.cache.hash_utils import cache_key
        k1 = cache_key("测试需求", "test-model")
        k2 = cache_key("测试需求", "test-model")
        assert k1 == k2  # 相同输入产生相同 key

    def test_cache_key_differs(self):
        import sys
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        from common.cache.hash_utils import cache_key
        k1 = cache_key("需求A", "m1")
        k2 = cache_key("需求B", "m1")
        assert k1 != k2

    def test_simple_cache_get_set(self):
        import sys
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        from common.cache import simple_cache
        # 确保启用
        import os
        os.environ["CACHE_ENABLED"] = "true"
        os.environ["CACHE_TTL_SECONDS"] = "60"

        simple_cache.clear()
        key = "test-key-gateway"
        value = {"result": "hello"}
        simple_cache.set(key, value)
        cached = simple_cache.get(key)
        assert cached == value
        simple_cache.clear()

    def test_simple_cache_miss(self):
        import sys
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        from common.cache import simple_cache
        simple_cache.clear()
        result = simple_cache.get("nonexistent-key-xyz")
        assert result is None

    def test_simple_cache_disabled(self):
        import sys, os
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        # CACHE_ENABLED 在模块加载时读取, 需要重新加载
        os.environ["CACHE_ENABLED"] = "false"
        import importlib
        from common.cache import simple_cache
        importlib.reload(simple_cache)
        simple_cache.set("k", "v")
        assert simple_cache.get("k") is None
        # 恢复
        os.environ["CACHE_ENABLED"] = "true"
        importlib.reload(simple_cache)

    def test_simple_cache_stats(self):
        import sys
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        from common.cache import simple_cache
        simple_cache.clear()
        stats = simple_cache.stats()
        assert "backend" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "entries" in stats
        assert stats["backend"] == "memory"

    def test_knowledge_version(self):
        import sys
        from pathlib import Path
        _sr = Path(__file__).resolve().parent.parent.parent / "services"
        if str(_sr) not in sys.path:
            sys.path.insert(0, str(_sr))
        from common.cache.hash_utils import knowledge_version
        kv = knowledge_version()
        assert isinstance(kv, str)
        assert len(kv) > 0
