"""LangGraph 编排工作流 — 将三个 Agent 调用建模为状态图节点.

如果 langgraph 未安装, build_workflow() 返回 None,
由 main.py 回退到手写编排 (现有逻辑).
"""

import logging
import time
from typing import Any, Dict, Optional

import httpx

from .workflow_state import ArchitectureWorkflowState

logger = logging.getLogger("api-gateway.langgraph")

# ── Agent 服务地址 ──
REQUIREMENTS_AGENT_URL = "http://localhost:8001"
MATCHING_AGENT_URL = "http://localhost:8002"
EVALUATION_AGENT_URL = "http://localhost:8003"


def _configure_urls(req_url: str, match_url: str, eval_url: str) -> None:
    global REQUIREMENTS_AGENT_URL, MATCHING_AGENT_URL, EVALUATION_AGENT_URL
    REQUIREMENTS_AGENT_URL = req_url
    MATCHING_AGENT_URL = match_url
    EVALUATION_AGENT_URL = eval_url


# ── 节点实现 ──────────────────────────────────────────────────


async def _extract_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """调用 requirements-agent 提取特征."""
    t0 = time.perf_counter()
    requirement = state.get("requirement", "")
    logger.info("[LangGraph] extract_node: calling requirements-agent...")
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(
                f"{REQUIREMENTS_AGENT_URL}/extract",
                json={"requirement": requirement},
            )
            resp.raise_for_status()
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"[LangGraph] extract_node done in {elapsed}ms")
        state.setdefault("trace", []).append({"node": "extract", "elapsed_ms": elapsed, "status": "ok"})
        return {
            "extracted_features": data["features"],
            "feature_hits": data.get("feature_hits", {}),
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append({"node": "extract", "elapsed_ms": elapsed, "status": "error", "error": str(e)})
        state.setdefault("errors", []).append(f"extract: {e}")
        raise


async def _match_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """调用 matching-agent 匹配架构风格."""
    t0 = time.perf_counter()
    features = state.get("extracted_features", {})
    logger.info("[LangGraph] match_node: calling matching-agent...")
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(
                f"{MATCHING_AGENT_URL}/match",
                json={"features": features},
            )
            resp.raise_for_status()
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"[LangGraph] match_node done in {elapsed}ms")
        state.setdefault("trace", []).append({"node": "match", "elapsed_ms": elapsed, "status": "ok"})
        return {
            "candidates": data.get("candidates", []),
            "combination_candidates": data.get("combination_candidates", []),
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append({"node": "match", "elapsed_ms": elapsed, "status": "error", "error": str(e)})
        state.setdefault("errors", []).append(f"match: {e}")
        raise


async def _evaluate_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """调用 evaluation-agent 进行评估."""
    t0 = time.perf_counter()
    requirement = state.get("requirement", "")
    features = state.get("extracted_features", {})
    candidates = state.get("candidates", [])
    logger.info("[LangGraph] evaluate_node: calling evaluation-agent...")
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(
                f"{EVALUATION_AGENT_URL}/evaluate",
                json={
                    "requirement": requirement,
                    "features": features,
                    "candidates": candidates,
                    "combination_candidates": state.get("combination_candidates", []),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"[LangGraph] evaluate_node done in {elapsed}ms")
        state.setdefault("trace", []).append({"node": "evaluate", "elapsed_ms": elapsed, "status": "ok"})
        return {"final_report": data}
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append({"node": "evaluate", "elapsed_ms": elapsed, "status": "error", "error": str(e)})
        state.setdefault("errors", []).append(f"evaluate: {e}")
        raise


async def _trace_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """追踪节点 — 记录整体状态摘要 (passthrough)."""
    trace = state.get("trace", [])
    errors = state.get("errors", [])
    total_ms = sum(t.get("elapsed_ms", 0) for t in trace) if trace else 0
    logger.info(
        f"[LangGraph] trace_node: {len(trace)} steps, "
        f"{total_ms}ms total, {len(errors)} errors"
    )
    return {"workflow_engine": "langgraph"}


# ── 工作流构建 ────────────────────────────────────────────────


def build_workflow(req_url: str = "http://localhost:8001",
                   match_url: str = "http://localhost:8002",
                   eval_url: str = "http://localhost:8003"):
    """构建 LangGraph 状态图工作流.

    Returns:
        CompiledStateGraph | None — None 表示 langgraph 不可用, 应回退手动编排.
    """
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        logger.warning("langgraph not installed, falling back to manual orchestration")
        return None

    _configure_urls(req_url, match_url, eval_url)

    try:
        workflow = StateGraph(ArchitectureWorkflowState)

        workflow.add_node("extract", _extract_node)
        workflow.add_node("match", _match_node)
        workflow.add_node("evaluate", _evaluate_node)
        workflow.add_node("trace", _trace_node)

        workflow.add_edge(START, "extract")
        workflow.add_edge("extract", "match")
        workflow.add_edge("match", "evaluate")
        workflow.add_edge("evaluate", "trace")
        workflow.add_edge("trace", END)

        compiled = workflow.compile()
        logger.info("LangGraph workflow compiled successfully")
        return compiled
    except Exception as e:
        logger.error(f"Failed to build LangGraph workflow: {e}")
        return None
