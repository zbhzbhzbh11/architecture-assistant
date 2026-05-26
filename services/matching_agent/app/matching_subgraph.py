"""Matching Subgraph — matching-agent 内部 3 子节点编排.

将原来 match() 函数内的三步串行:
  规则评分 → 图谱融合 → 组合推荐
拆分为 3 个独立子节点, 编译为 LangGraph Subgraph。

【子图拓扑】
  START → rule_score → graph_blend → combo_rank → END

【与 common.matching 的关系】
score_style / select_top3 / blend_scores / rank_combinations
全部从 common.matching 导入 —— 纯函数, 可在测试中独立验证.
"""

import logging
import time
from typing import Any, Dict, List, Optional, TypedDict

import httpx

from common.matching import (
    score_style, select_top3, blend_scores, rank_combinations,
)

logger = logging.getLogger("matching-agent.subgraph")

# 由 build_matching_subgraph() 注入
KNOWLEDGE_BASE_URL = "http://localhost:8004"


def _configure_kb_url(kb_url: str) -> None:
    global KNOWLEDGE_BASE_URL
    KNOWLEDGE_BASE_URL = kb_url


# ═══════════════════════════════════════════════════════════
# 三个子节点
# ═══════════════════════════════════════════════════════════


async def _rule_score_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 1: 从 knowledge-base 拉取 styles + weights, 逐风格规则评分."""
    t0 = time.perf_counter()
    features = state.get("features", {})
    logger.info("[subgraph] rule_score: fetching styles...")

    async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
        resp = await client.get(f"{KNOWLEDGE_BASE_URL}/styles")
        resp.raise_for_status()
        styles = resp.json()["styles"]

        learned_weights: Dict[str, Dict[str, int]] = {}
        try:
            lw_resp = await client.get(f"{KNOWLEDGE_BASE_URL}/feedback/weights")
            lw_resp.raise_for_status()
            learned_weights = lw_resp.json().get("weights", {})
        except Exception:
            pass

    llm_disputed = state.get("llm_disputed", {})
    arch_inclination = state.get("arch_inclination", {})
    scored = [score_style(s, features, learned_weights, llm_disputed) for s in styles]

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] rule_score done: {len(scored)} styles, {elapsed}ms")
    return {"rule_scored": scored, "_trace_rule_score": elapsed}


async def _graph_blend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 2: 排序 + Top 3 候选选择 (图谱匹配已由标签匹配替代)."""
    t0 = time.perf_counter()
    rule_scored = state.get("rule_scored", [])

    # 直接按规则评分排序选 Top3, 不再单独查询图谱
    # (HAS_QUALITY 关系数据已通过标签匹配在 score_style 中体现)
    rule_scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = select_top3(rule_scored)

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] graph_blend done: {[c['style'] for c in candidates]}, {elapsed}ms")
    return {
        "blended_scores": rule_scored,
        "graph_evidence": {},
        "candidates": candidates,
        "_trace_graph_blend": elapsed,
    }


async def _combo_rank_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 3: 组合推荐评分排序."""
    t0 = time.perf_counter()
    blended = state.get("blended_scores", [])
    graph_evidence = state.get("graph_evidence") or None
    features = state.get("features", {})

    combo_candidates: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{KNOWLEDGE_BASE_URL}/combinations")
            resp.raise_for_status()
            combos = resp.json().get("combinations", [])

        if combos:
            scored_by_name = {item["style"]: item for item in blended}
            combo_candidates = rank_combinations(
                combos, scored_by_name, features, graph_evidence, top_n=3,
            )
    except Exception as e:
        logger.warning(f"[subgraph] Combination ranking failed (non-fatal): {e}")

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] combo_rank done: {len(combo_candidates)} combinations, {elapsed}ms")
    return {"combination_candidates": combo_candidates, "_trace_combo_rank": elapsed}


# ═══════════════════════════════════════════════════════════
# 子图工厂
# ═══════════════════════════════════════════════════════════

class MatchSubgraphState(TypedDict, total=False):
    """TypedDict 定义各字段独立 channel — 防止节点返回值相互覆盖."""
    features: Dict[str, bool]
    llm_disputed: Dict[str, bool]
    arch_inclination: Dict[str, Any]
    rule_scored: List[Dict[str, Any]]
    blended_scores: List[Dict[str, Any]]
    graph_evidence: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]]
    _trace_rule_score: int
    _trace_graph_blend: int
    _trace_combo_rank: int


def build_matching_subgraph(kb_url: str = "http://localhost:8004"):
    """编译 matching 子图: rule_score → graph_blend → combo_rank.

    Returns:
        CompiledStateGraph | None — None 表示 langgraph 不可用.
    """
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        logger.warning("langgraph not installed, subgraph unavailable")
        return None

    _configure_kb_url(kb_url)

    try:
        subgraph = StateGraph(MatchSubgraphState)

        subgraph.add_node("rule_score", _rule_score_node)
        subgraph.add_node("graph_blend", _graph_blend_node)
        subgraph.add_node("combo_rank", _combo_rank_node)

        subgraph.add_edge(START, "rule_score")
        subgraph.add_edge("rule_score", "graph_blend")
        subgraph.add_edge("graph_blend", "combo_rank")
        subgraph.add_edge("combo_rank", END)

        compiled = subgraph.compile()
        logger.info("Matching subgraph compiled (3 sub-nodes)")
        return compiled
    except Exception as e:
        logger.error(f"Failed to build matching subgraph: {e}")
        return None
