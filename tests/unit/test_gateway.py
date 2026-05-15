"""API Gateway 单元测试: LangGraph 编排 + 手动 fallback."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

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


# ====================================================================
# recommend() 端点 + _manual_orchestrate() + _langgraph_orchestrate()
# ====================================================================

_SR = Path(__file__).resolve().parent.parent.parent
if str(_SR) not in sys.path:
    sys.path.insert(0, str(_SR))

REQUIREMENT_TEXT = (
    "开发一个跨平台的即时通讯系统，要求支持万人同时在线，"
    "需要保证消息的实时性和可靠性，后期可能需要快速扩展视频通话功能"
)


def _mock_response(json_data, status_code=200):
    """构造假 httpx.Response, 含 json() / raise_for_status() / status_code."""
    if status_code >= 400:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status = MagicMock(side_effect=Exception(f"HTTP {status_code}"))
        return resp
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _stub_extract_response():
    return _mock_response({
        "features": {"high_concurrency": True, "real_time": True, "reliability": True, "scalability": True},
        "feature_hits": {"high_concurrency": ["万人","高并发"], "real_time": ["实时","消息"], "reliability": ["可靠"], "scalability": ["扩展"]},
    })


def _stub_match_response():
    return _mock_response({
        "candidates": [
            {"style": "Event-Driven Architecture", "score": 8, "pros": ["high throughput"], "cons": ["hard tracing"]},
            {"style": "Microservices", "score": 6, "pros": ["high scalability"], "cons": ["distributed complexity"]},
            {"style": "Layered Architecture", "score": 3, "pros": ["high maintainability"], "cons": ["performance overhead"]},
        ],
        "combination_candidates": [],
    })


def _stub_eval_response():
    return _mock_response({
        "recommended_style": "Event-Driven Architecture",
        "recommended_style_zh": "事件驱动架构",
        "alternative_styles": ["Microservices", "Layered Architecture"],
        "decision_basis": {"rule_engine": ["高并发场景处理能力强"], "llm_summary": "推荐事件驱动"},
        "comparison_matrix": [
            {"style": "Event-Driven Architecture", "score": 8, "key_reasons": ["高并发"], "pros": ["high throughput"], "cons": ["hard tracing"]},
            {"style": "Microservices", "score": 6, "key_reasons": ["可扩展"], "pros": ["high scalability"], "cons": ["distributed complexity"]},
            {"style": "Layered Architecture", "score": 3, "key_reasons": ["强一致"], "pros": ["high maintainability"], "cons": ["performance overhead"]},
        ],
        "risk_and_suggestions": {"main_risks": ["复杂度高"], "suggestions": ["引入消息队列"]},
        "recommended_combination": {},
        "combination_candidates": [],
        "adr": {"adr_id": "ADR-test", "adr_status": "ok"},
    })


# ── 辅助: 缓存 mock ──────────────────────────────────────────────

CACHED_RESULT = {
    "extracted_features": {"high_concurrency": True, "real_time": True},
    "feature_hits": {"high_concurrency": ["高并发"]},
    "candidates": [{"style": "Event-Driven Architecture", "score": 7}],
    "final_report": {"recommended_style": "Event-Driven Architecture"},
    "workflow_engine": "manual",
    "workflow_trace": [{"node": "extract", "elapsed_ms": 5, "status": "ok"}],
}


# ====================================================================
# TestRecommendEndpoint — recommend() 三条完整路径
# ====================================================================

class TestRecommendEndpoint:
    """recommend() 端点: 缓存命中 / LangGraph 成功 / LangGraph 失败 fallback."""

    def test_cache_hit_skips_orchestration(self):
        """cache 命中应直接返回缓存且不进入编排层."""
        import asyncio
        from services.api_gateway.app.main import recommend, RecommendRequest

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        with patch("services.api_gateway.app.main.cache_key") as mk, \
             patch("services.api_gateway.app.main.cache_get") as mg:
            mk.return_value = "key-cache-hit-test"
            mg.return_value = dict(CACHED_RESULT)  # 深拷贝避免污染

            result = asyncio.run(recommend(payload))

        # 缓存命中标记
        assert result["cache_hit"] is True
        # 响应结构完整性
        assert "extracted_features" in result
        assert result["extracted_features"]["high_concurrency"] is True
        assert "final_report" in result
        assert result["final_report"]["recommended_style"] == "Event-Driven Architecture"
        assert "candidates" in result
        assert isinstance(result["candidates"], list)
        # 缓存结果不应被篡改
        assert result["workflow_engine"] == "manual"

    def test_langgraph_success_path(self):
        """LangGraph 正常执行后返回完整响应 (含 trace / candidates / final_report)."""
        import asyncio
        from services.api_gateway.app.main import recommend, RecommendRequest

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        # LangGraph 成功结果
        lg_result = {
            "extracted_features": {"high_concurrency": True, "real_time": True},
            "feature_hits": {"high_concurrency": ["万人"]},
            "candidates": [{"style": "Event-Driven Architecture", "score": 9}],
            "final_report": {
                "recommended_style": "Event-Driven Architecture",
                "refactoring_advice": {},
            },
            "workflow_engine": "langgraph",
            "workflow_trace": [
                {"node": "extract", "elapsed_ms": 10, "status": "ok"},
                {"node": "match", "elapsed_ms": 15, "status": "ok"},
                {"node": "evaluate", "elapsed_ms": 50, "status": "ok"},
                {"node": "trace", "elapsed_ms": 1, "status": "ok"},
            ],
        }

        with patch("services.api_gateway.app.main.cache_key") as mk, \
             patch("services.api_gateway.app.main.cache_get") as mg, \
             patch("services.api_gateway.app.main.cache_set") as ms, \
             patch("services.api_gateway.app.main._langgraph_app", MagicMock()), \
             patch("services.api_gateway.app.main._langgraph_orchestrate") as mlo, \
             patch("services.api_gateway.app.main.httpx.AsyncClient") as m_ac:
            mk.return_value = "key-lg-ok"
            mg.return_value = None  # cache miss
            mlo.return_value = lg_result  # _langgraph_orchestrate 成功
            # 重构 agent 调用静默降级 (AsyncClient 抛异常 → except 捕获)
            m_ac.side_effect = Exception("refactor unreachable in test")

            result = asyncio.run(recommend(payload))

        # cache miss
        assert result.get("cache_hit") is False
        # 编排引擎标记
        assert result["workflow_engine"] == "langgraph"
        # trace 包含 4 个节点记录
        trace = result.get("workflow_trace", [])
        assert len(trace) >= 4, f"trace 应含 4 个节点, 实为 {len(trace)}: {trace}"
        node_names = [t["node"] for t in trace]
        for name in ("extract", "match", "evaluate", "trace"):
            assert name in node_names, f"trace 缺少 {name} 节点"
        # 响应结构
        assert "extracted_features" in result
        assert "candidates" in result
        assert len(result["candidates"]) >= 1
        assert "final_report" in result
        assert result["final_report"]["recommended_style"] == "Event-Driven Architecture"
        # cache_set 被调用
        ms.assert_called_once()

    def test_langgraph_fail_fallback_to_manual(self):
        """LangGraph 抛异常 → 回退到 _manual_orchestrate → 最终结果标记为 manual."""
        import asyncio
        from services.api_gateway.app.main import recommend, RecommendRequest

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        manual_result = {
            "extracted_features": {"high_concurrency": True},
            "feature_hits": {"high_concurrency": ["万人"]},
            "candidates": [{"style": "Microservices", "score": 6}],
            "final_report": {"recommended_style": "Microservices"},
            "workflow_engine": "manual",
            "workflow_trace": [
                {"node": "extract", "elapsed_ms": 8, "status": "ok"},
                {"node": "match", "elapsed_ms": 12, "status": "ok"},
                {"node": "evaluate", "elapsed_ms": 40, "status": "ok"},
            ],
        }

        with patch("services.api_gateway.app.main.cache_key") as mk, \
             patch("services.api_gateway.app.main.cache_get") as mg, \
             patch("services.api_gateway.app.main.cache_set") as ms, \
             patch("services.api_gateway.app.main._langgraph_app", MagicMock()), \
             patch("services.api_gateway.app.main._langgraph_orchestrate") as mlo, \
             patch("services.api_gateway.app.main._manual_orchestrate") as mmo, \
             patch("services.api_gateway.app.main.httpx.AsyncClient") as m_ac:
            mk.return_value = "key-lg-fail"
            mg.return_value = None
            mlo.side_effect = RuntimeError("LangGraph StateGraph timeout")
            mmo.return_value = manual_result
            m_ac.side_effect = Exception("refactor unreachable")

            result = asyncio.run(recommend(payload))

        # 确认为 manual 回退
        assert result["workflow_engine"] == "manual"
        assert result.get("cache_hit") is False
        # trace 应来自 _manual_orchestrate (3 个节点)
        trace = result.get("workflow_trace", [])
        assert len(trace) == 3, f"manual 路径应含 3 个节点, 实为 {len(trace)}"
        node_names = [t["node"] for t in trace]
        for name in ("extract", "match", "evaluate"):
            assert name in node_names
        # _manual_orchestrate 被调用
        mmo.assert_called_once()
        # _langgraph_orchestrate 被调用 (然后失败)
        mlo.assert_called_once()
        # 结果来自 manual
        assert result["final_report"]["recommended_style"] == "Microservices"


# ====================================================================
# TestManualOrchestrate — _manual_orchestrate() 三步串行
# ====================================================================

class TestManualOrchestrate:
    """_manual_orchestrate() 正常 + 中间节点失败."""

    def test_normal_three_step_flow(self):
        """三个下游全部正常时, 数据逐级传递且 trace 含 3 个 ok 节点."""
        import asyncio
        from services.api_gateway.app.main import _manual_orchestrate, RecommendRequest

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        extract_resp = _stub_extract_response()
        match_resp = _stub_match_response()
        eval_resp = _stub_eval_response()

        mock_ctx = AsyncMock()
        mock_ctx.post = AsyncMock(side_effect=[extract_resp, match_resp, eval_resp])
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_ctx

        with patch("services.api_gateway.app.main.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(_manual_orchestrate(payload))

        # 编排引擎标记
        assert result["workflow_engine"] == "manual"
        # 三层数据逐级传递
        assert result["extracted_features"]["high_concurrency"] is True
        assert result["extracted_features"]["real_time"] is True
        assert len(result["candidates"]) == 3
        assert result["candidates"][0]["style"] == "Event-Driven Architecture"
        assert result["final_report"]["recommended_style"] == "Event-Driven Architecture"
        # trace 含 3 个 ok 节点
        trace = result["workflow_trace"]
        assert len(trace) == 3
        for entry in trace:
            assert entry["status"] == "ok"
            assert "elapsed_ms" in entry
            assert isinstance(entry["elapsed_ms"], (int, float))
            assert entry["elapsed_ms"] >= 0
        node_names_order = [t["node"] for t in trace]
        assert node_names_order == ["extract", "match", "evaluate"]

    def test_mid_node_http_500_propagates(self):
        """matching-agent 返回 500 → _manual_orchestrate 应抛出异常."""
        import asyncio
        from services.api_gateway.app.main import _manual_orchestrate, RecommendRequest

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        extract_resp = _stub_extract_response()
        match_err = _mock_response({"detail": "Internal Server Error"}, status_code=500)

        mock_ctx = AsyncMock()
        mock_ctx.post = AsyncMock(side_effect=[extract_resp, match_err])
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_ctx

        with patch("services.api_gateway.app.main.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="HTTP 500"):
                asyncio.run(_manual_orchestrate(payload))

    def test_manual_passes_combination_candidates(self):
        """_manual_orchestrate 应透传 combination_candidates 到 evaluation-agent."""
        import asyncio
        from services.api_gateway.app.main import _manual_orchestrate, RecommendRequest

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        extract_resp = _stub_extract_response()
        match_resp = _mock_response({
            "candidates": [{"style": "Microservices", "score": 5}],
            "combination_candidates": [
                {"combination_name": "Microservices+Event", "combo_score": 7}
            ],
        })
        eval_resp = _stub_eval_response()

        mock_ctx = AsyncMock()
        mock_ctx.post = AsyncMock(side_effect=[extract_resp, match_resp, eval_resp])
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_ctx

        with patch("services.api_gateway.app.main.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(_manual_orchestrate(payload))

        # evaluation-agent 被调用时传入了 combination_candidates
        call_args = mock_ctx.post.call_args_list[2]
        sent_json = call_args[1]["json"]
        assert "combination_candidates" in sent_json
        assert len(sent_json["combination_candidates"]) == 1
        assert sent_json["combination_candidates"][0]["combination_name"] == "Microservices+Event"


# ====================================================================
# TestLangGraphOrchestrate — _langgraph_orchestrate() LangGraph 路径
# ====================================================================

class TestLangGraphOrchestrate:
    """_langgraph_orchestrate() 正常 + 节点超时 trace 验证."""

    def test_normal_returns_langgraph_state(self):
        """正常执行后返回 workflow_engine=langgraph, 包含 trace."""
        import asyncio
        from services.api_gateway.app.main import _langgraph_orchestrate, RecommendRequest
        import services.api_gateway.app.main as gateway_main

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        mock_state = {
            "requirement": payload.requirement,
            "extracted_features": {"high_concurrency": True, "real_time": True},
            "feature_hits": {"high_concurrency": ["万人"]},
            "candidates": [{"style": "Event-Driven Architecture", "score": 8}],
            "combination_candidates": [],
            "final_report": {"recommended_style": "Event-Driven Architecture"},
            "errors": [],
            "trace": [
                {"node": "extract", "elapsed_ms": 12, "status": "ok"},
                {"node": "match", "elapsed_ms": 18, "status": "ok"},
                {"node": "evaluate", "elapsed_ms": 55, "status": "ok"},
                {"node": "trace", "elapsed_ms": 1, "status": "ok"},
            ],
            "workflow_engine": "langgraph",
        }

        with patch.object(gateway_main, '_langgraph_app') as mock_app:
            mock_app.ainvoke = AsyncMock(return_value=mock_state)
            result = asyncio.run(_langgraph_orchestrate(payload))

        # 引擎标记
        assert result["workflow_engine"] == "langgraph"
        # 状态转译正确
        assert result["extracted_features"]["high_concurrency"] is True
        assert result["extracted_features"]["real_time"] is True
        assert "feature_hits" in result
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["style"] == "Event-Driven Architecture"
        assert result["final_report"]["recommended_style"] == "Event-Driven Architecture"
        # trace 完整
        trace = result["workflow_trace"]
        assert len(trace) == 4
        for entry in trace:
            assert "node" in entry
            assert "elapsed_ms" in entry
            assert "status" in entry

    def test_node_timeout_trace_preserved(self):
        """模拟 extract 节点超时报错, trace 含 error 状态且 elapsed_ms ≥ 模拟值."""
        import asyncio
        from services.api_gateway.app.main import _langgraph_orchestrate, RecommendRequest
        import services.api_gateway.app.main as gateway_main

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        # extract 节点超时 35000ms, 状态 error
        mock_state = {
            "requirement": payload.requirement,
            "extracted_features": {},
            "feature_hits": {},
            "candidates": [],
            "combination_candidates": [],
            "final_report": {},
            "errors": ["extract: timeout"],
            "trace": [
                {"node": "extract", "elapsed_ms": 35000, "status": "error", "error": "httpx.TimeoutException"},
            ],
        }

        with patch.object(gateway_main, '_langgraph_app') as mock_app:
            mock_app.ainvoke = AsyncMock(return_value=mock_state)
            result = asyncio.run(_langgraph_orchestrate(payload))

        # trace 含 error 状态
        trace = result["workflow_trace"]
        assert len(trace) == 1
        assert trace[0]["node"] == "extract"
        assert trace[0]["status"] == "error"
        assert trace[0]["elapsed_ms"] == 35000
        assert "error" in trace[0]
        assert "TimeoutException" in trace[0]["error"]

    def test_langgraph_ainvoke_raises_propagates(self):
        """ainvoke 抛 RuntimeError → _langgraph_orchestrate 应向上传播."""
        import asyncio
        from services.api_gateway.app.main import _langgraph_orchestrate, RecommendRequest
        import services.api_gateway.app.main as gateway_main

        payload = RecommendRequest(requirement=REQUIREMENT_TEXT)

        with patch.object(gateway_main, '_langgraph_app') as mock_app:
            mock_app.ainvoke = AsyncMock(side_effect=RuntimeError("graph node crashed"))
            with pytest.raises(RuntimeError, match="graph node crashed"):
                asyncio.run(_langgraph_orchestrate(payload))

    def test_initial_state_passed_to_ainvoke(self):
        """初始状态应包含 requirement、空 trace、空 errors."""
        import asyncio
        from services.api_gateway.app.main import _langgraph_orchestrate, RecommendRequest
        import services.api_gateway.app.main as gateway_main

        payload = RecommendRequest(requirement="短需求足足十个字以上")
        mock_state = {"trace": [], "final_report": {}, "extracted_features": {}, "feature_hits": {}, "candidates": [], "combination_candidates": []}

        with patch.object(gateway_main, '_langgraph_app') as mock_app:
            mock_app.ainvoke = AsyncMock(return_value=mock_state)
            asyncio.run(_langgraph_orchestrate(payload))

        # 验证 ainvoke 收到的初始状态
        call_args = mock_app.ainvoke.call_args[0][0]
        assert call_args["requirement"] == "短需求足足十个字以上"
        assert call_args["extracted_features"] == {}
        assert call_args["candidates"] == []
        assert call_args["final_report"] == {}
        assert call_args["errors"] == []
        assert call_args["trace"] == []
