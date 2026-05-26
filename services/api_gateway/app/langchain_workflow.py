"""LangGraph StateGraph 编排 — extract, match, evaluate, trace.

matching-agent Subgraph: rule_score → graph_blend → combo_rank (3子节点)
evaluation-agent Subgraph: sort → Send(vote || summary) → merge (4子节点, 并行扇出)
"""


import logging
import time
from typing import Any, Dict, Optional

import httpx

from .workflow_state import ArchitectureWorkflowState

logger = logging.getLogger("api-gateway.langgraph")

# Agent 服务地址 — 在 build_workflow() 中被 _configure_urls() 覆写为 Docker 容器名
REQUIREMENTS_AGENT_URL = "http://localhost:8001"
MATCHING_AGENT_URL = "http://localhost:8002"
EVALUATION_AGENT_URL = "http://localhost:8003"


def _configure_urls(req_url: str, match_url: str, eval_url: str) -> None:
    """将 Docker 容器名注入三个全局 URL 变量.

    本地开发时是 localhost:800x, Docker 中是 requirements-agent:8001 等.
    这个函数在 build_workflow() 编译前被调用.
    """
    global REQUIREMENTS_AGENT_URL, MATCHING_AGENT_URL, EVALUATION_AGENT_URL
    REQUIREMENTS_AGENT_URL = req_url
    MATCHING_AGENT_URL = match_url
    EVALUATION_AGENT_URL = eval_url


# ═══════════════════════════════════════════════════════════════
# 四个状态图节点 — 每个节点是一个独立的 HTTP 调用
# 节点签名: async def node(state) -> Dict[str, Any]
#   - 入参 state:  图全局状态 (TypedDict, 所有字段可选)
#   - 返回值:      要更新到 state 中的字段字典 (shallow merge)
# ═══════════════════════════════════════════════════════════════


async def _extract_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """【节点1】调用 requirements-agent 提取需求特征.

    输入:  state["requirement"] (用户输入的自然语言需求文本)
    输出:  state["extracted_features"]     示例: {"high_concurrency": True, ...}
           state["feature_hits"]           示例: {"high_concurrency": ["万人","高并发"]}

    耗时记录到 state["trace"]: {"node": "extract", "elapsed_ms": 292, "status": "ok"}

    异常处理:
      - HTTP 异常 → raise, 由 main.py 的 try/except 捕获并记录
      - trace 仍记录 error 状态和耗时用于调试
    """
    t0 = time.perf_counter()
    requirement = state.get("requirement", "")
    logger.info("[LangGraph] extract_node: calling requirements-agent...")
    try:
        # httpx.AsyncClient 异步 HTTP 客户端
        # trust_env=False 跳过系统代理设置 (避免 Docker 环境下代理干扰)
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(
                f"{REQUIREMENTS_AGENT_URL}/extract",
                json={"requirement": requirement},
            )
            resp.raise_for_status()
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"[LangGraph] extract_node done in {elapsed}ms")
        state.setdefault("trace", []).append(
            {"node": "extract", "elapsed_ms": elapsed, "status": "ok"}
        )
        return {
            "extracted_features": data["features"],
            "feature_hits": data.get("feature_hits", {}),
            "llm_disputed": data.get("llm_disputed", {}),
            "arch_inclination": data.get("arch_inclination", {}),
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append(
            {"node": "extract", "elapsed_ms": elapsed, "status": "error", "error": str(e)}
        )
        state.setdefault("errors", []).append(f"extract: {e}")
        raise


async def _match_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """【节点2】调用 matching-agent 匹配架构风格.

    输入:  state["extracted_features"] (从上个节点继承的特征 bool 字典)
    输出:  state["candidates"]             候选架构列表 (3个,按分排序)
           state["combination_candidates"] 组合架构推荐 (最多3个)

    matching-agent 内部并行执行: 规则引擎评分 (score_style) + 图谱引擎评分 (POST /graph/score),
    在 blend 节点加权融合后选出 Top 3.
    """
    t0 = time.perf_counter()
    features = state.get("extracted_features", {})
    llm_disputed = state.get("llm_disputed", {})
    arch_inclination = state.get("arch_inclination", {})
    logger.info("[LangGraph] match_node: calling matching-agent...")
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(
                f"{MATCHING_AGENT_URL}/match",
                json={"features": features, "llm_disputed": llm_disputed,
                          "arch_inclination": arch_inclination},
            )
            resp.raise_for_status()
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"[LangGraph] match_node done in {elapsed}ms")
        state.setdefault("trace", []).append(
            {"node": "match", "elapsed_ms": elapsed, "status": "ok"}
        )
        return {
            "candidates": data.get("candidates", []),
            "combination_candidates": data.get("combination_candidates", []),
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append(
            {"node": "match", "elapsed_ms": elapsed, "status": "error", "error": str(e)}
        )
        state.setdefault("errors", []).append(f"match: {e}")
        raise


async def _evaluate_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """【节点3】调用 evaluation-agent 进行评估决策.

    输入:  state["requirement"] + state["features"] + state["candidates"]
    输出:  state["final_report"]  完整报告:
            {recommended_style, alternative_styles, comparison_matrix,
             decision_basis, risk_and_suggestions, recommended_combination,
             adr, ...}

    evaluation-agent 内部: 规则排序 → LLM 并行投票+摘要 (asyncio.gather)
    → 混合推理 → LLM 投票 tie-break → ADR 自动生成
    """
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
                "llm_disputed": state.get("llm_disputed", {}),
                    "candidates": candidates,
                    "combination_candidates": state.get("combination_candidates", []),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"[LangGraph] evaluate_node done in {elapsed}ms")
        state.setdefault("trace", []).append(
            {"node": "evaluate", "elapsed_ms": elapsed, "status": "ok"}
        )
        return {"final_report": data}
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append(
            {"node": "evaluate", "elapsed_ms": elapsed, "status": "error", "error": str(e)}
        )
        state.setdefault("errors", []).append(f"evaluate: {e}")
        raise


async def _trace_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    """【节点4】追踪汇总 — 只读节点, 不产生新数据.

    汇总所有上游节点的 trace 和 errors, 输出总耗时和错误数到日志.
    前端用 workflow_trace 渲染各节点的耗时条状图.
    """
    trace = state.get("trace", [])
    errors = state.get("errors", [])
    total_ms = sum(t.get("elapsed_ms", 0) for t in trace) if trace else 0
    logger.info(
        f"[LangGraph] trace_node: {len(trace)} steps, "
        f"{total_ms}ms total, {len(errors)} errors"
    )
    return {"workflow_engine": "langgraph"}


# ═══════════════════════════════════════════════════════════════
# 工作流构建 — 模块唯一对外接口
# ═══════════════════════════════════════════════════════════════


def build_workflow(
    req_url: str = "http://localhost:8001",
    match_url: str = "http://localhost:8002",
    eval_url: str = "http://localhost:8003",
):
    """构建 LangGraph StateGraph 并编译为可执行图.

    【四个节点】
      extract → match → evaluate → trace

    【状态管理】
      ArchitectureWorkflowState (TypedDict, 所有字段可选)
      节点通过返回值做 shallow merge 更新状态
      每个节点只读写自己的字段, 互不干扰

    【容错】
      - langgraph 未安装 → 返回 None, 抛出明确错误提示安装
      - 图编译异常 → 返回 None, 同上
      - 节点运行时异常 → raise, 由上层 try/except 捕获并记录

    Returns:
        CompiledStateGraph | None
    """
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        logger.warning("langgraph not installed, workflow unavailable")
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
