"""Matching Subgraph — 双驱动并行架构 (规则引擎 ∥ 图谱引擎).

Send() 声明 rule_score 和 graph_score 两个评分路径并行执行,
在 blend 节点加权融合, 任一分支失败时独立降级.

【子图拓扑】
  START → Send(rule_score ∥ graph_score) → blend → combo_rank → END
"""

import logging
import time
from typing import Any, Dict, List, TypedDict

import httpx

from common.matching import (
    score_style, select_top3, rank_combinations,
)

logger = logging.getLogger("matching-agent.subgraph")

KNOWLEDGE_BASE_URL = "http://localhost:8004"


def _configure_kb_url(kb_url: str) -> None:
    global KNOWLEDGE_BASE_URL
    KNOWLEDGE_BASE_URL = kb_url


# ═══════════════════════════════════════════════════════════════
# 并行子节点: 规则引擎评分 + 图谱引擎评分
# ═══════════════════════════════════════════════════════════════


async def _rule_score_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """并行分支 A: Python 规则引擎评分 — 5 层确定性评分."""
    t0 = time.perf_counter()
    features = state.get("features", {})
    logger.info("[subgraph] rule_score: fetching styles (parallel with graph_score)...")

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
    scored = [score_style(s, features, learned_weights, llm_disputed) for s in styles]

    elapsed = round((time.perf_counter() - t0) * 1000)
    top_scores = sorted(scored, key=lambda x: x["score"], reverse=True)[:3]
    logger.info(f"[subgraph] rule_score done: top3={[(c['style'], c['score']) for c in top_scores]}, {elapsed}ms")
    return {"rule_scored": scored, "_trace_rule_score": elapsed}


async def _graph_score_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """并行分支 B: Neo4j 图谱引擎评分 — Cypher 4 层图遍历评分."""
    t0 = time.perf_counter()
    features = state.get("features", {})
    logger.info("[subgraph] graph_score: calling POST /graph/score (parallel with rule_score)...")

    graph_scored: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.post(
                f"{KNOWLEDGE_BASE_URL}/graph/score",
                json={"features": features},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("available") and data.get("scored"):
                graph_scored = data["scored"]
                logger.info(f"[subgraph] graph_score returned {len(graph_scored)} styles")
            else:
                logger.warning(f"[subgraph] graph_score unavailable: {data.get('reason', 'unknown')}")
    except Exception as e:
        logger.warning(f"[subgraph] graph_score failed (will fallback to rule-only): {e}")

    elapsed = round((time.perf_counter() - t0) * 1000)
    top_scores = sorted(graph_scored, key=lambda x: x.get("graph_score", 0), reverse=True)[:3]
    logger.info(f"[subgraph] graph_score done: top3={[(c['style'], c.get('graph_score', 0)) for c in top_scores]}, {elapsed}ms")
    return {"graph_scored": graph_scored, "_trace_graph_score": elapsed}


# ═══════════════════════════════════════════════════════════════
# 融合节点: 规则引擎 + 图谱引擎 加权融合
# ═══════════════════════════════════════════════════════════════


async def _blend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """融合节点: 规则评分 + 图谱评分 → 加权融合 → select_top3.

    容错设计:
      - 两边都有结果 → 加权融合 (规则 60% + 图谱 40%)
      - 只有规则结果 → 纯规则引擎
      - 只有图谱结果 → 纯图谱引擎
      - 都没有 → 主流保底
    """
    t0 = time.perf_counter()
    rule_scored = state.get("rule_scored", [])
    graph_scored = state.get("graph_scored", [])

    # 量纲对齐日志
    if rule_scored:
        rule_max = max(c["score"] for c in rule_scored)
        rule_min = min(c["score"] for c in rule_scored)
        logger.info(f"[subgraph] blend: rule score range [{rule_min}, {rule_max}]")
    if graph_scored:
        graph_max = max(c.get("graph_score", 0) for c in graph_scored)
        graph_min = min(c.get("graph_score", 0) for c in graph_scored)
        logger.info(f"[subgraph] blend: graph score range [{graph_min}, {graph_max}]")

    # 构建风格名 → 分数映射
    by_name: Dict[str, Dict[str, float]] = {}
    features = state.get("features", {})

    for item in rule_scored:
        name = item["style"]
        by_name.setdefault(name, {})["rule"] = item["score"]

    # 图谱评分带完整证据 (matched_attributes/scenarios/risks/complements)
    graph_evidence: Dict[str, Dict[str, Any]] = {}
    for item in graph_scored:
        name = item["style"]
        by_name.setdefault(name, {})["graph"] = item.get("graph_score", 0)
        graph_evidence[name] = {
            "matched_attributes": item.get("matched_attributes", []),
            "matched_scenarios": item.get("matched_scenarios", []),
            "related_risks": item.get("related_risks", []),
            "combinable_styles": item.get("combinable_styles", []),
        }

    # 从 styles API 获取风格元数据 (用于填充 pros_zh/cons_zh/topology 等)
    style_meta: Dict[str, Dict[str, Any]] = {}
    if rule_scored:
        style_meta = {s["style"]: s for s in rule_scored}

    # 加权融合
    blended = []
    GRAPH_WEIGHT = 0.4
    RULE_WEIGHT = 0.6
    has_rule = any("rule" in v for v in by_name.values())
    has_graph = any("graph" in v for v in by_name.values())

    for name, scores in by_name.items():
        rule_s = scores.get("rule", 0)
        graph_s = scores.get("graph", 0)

        if has_rule and has_graph:
            final = round(rule_s * RULE_WEIGHT + graph_s * GRAPH_WEIGHT, 1)
            logger.debug(f"  blend: {name} rule={rule_s} graph={graph_s} → {final}")
        elif has_rule:
            final = rule_s
        elif has_graph:
            final = graph_s
        else:
            final = 0

        meta = style_meta.get(name, {})
        ev = graph_evidence.get(name, {})
        entry = {
            "style": name,
            "style_zh": meta.get("style_zh", name),
            "rule_score": rule_s,
            "graph_score": graph_s,
            "score": int(final),
            "score_raw": final,
            # 合并规则理由 + 图谱证据
            "reasons": meta.get("reasons", []) + [
                f"图谱: {attr}" for attr in ev.get("matched_attributes", [])
            ],
            "pros": meta.get("pros", []),
            "pros_zh": meta.get("pros_zh", []),
            "cons": meta.get("cons", []),
            "cons_zh": meta.get("cons_zh", []),
            "best_for": meta.get("best_for", []),
            "best_for_zh": meta.get("best_for_zh", []),
            "topology_mermaid": meta.get("topology_mermaid", ""),
            "matched_attributes": ev.get("matched_attributes", []),
            "matched_scenarios": ev.get("matched_scenarios", []),
            "related_risks": ev.get("related_risks", []),
            "combinable_styles": ev.get("combinable_styles", []),
            "graph_score_raw": graph_s,
        }
        blended.append(entry)

    candidates = select_top3(blended)

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] blend done: candidates={[c['style'] + ':' + str(c['score']) for c in candidates]}, "
                f"rule={'Y' if has_rule else 'N'}, graph={'Y' if has_graph else 'N'}, {elapsed}ms")
    return {
        "blended": blended,
        "candidates": candidates,
        "graph_evidence": graph_evidence,
        "_trace_blend": elapsed,
    }


# ═══════════════════════════════════════════════════════════════
# 组合推荐节点
# ═══════════════════════════════════════════════════════════════


async def _combo_rank_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 4: 组合推荐评分排序."""
    t0 = time.perf_counter()
    blended = state.get("blended", [])
    graph_evidence = state.get("graph_evidence") or {}
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


# ═══════════════════════════════════════════════════════════════
# 子图状态 + 工厂
# ═══════════════════════════════════════════════════════════════


class MatchSubgraphState(TypedDict, total=False):
    """TypedDict 各字段为独立 channel — 并行 Send() 写入互不覆盖."""
    features: Dict[str, bool]
    llm_disputed: Dict[str, bool]
    arch_inclination: Dict[str, Any]
    # 并行分支产出 — 两个独立字段, 同时写入不冲突
    rule_scored: List[Dict[str, Any]]
    graph_scored: List[Dict[str, Any]]
    # 融合产出
    blended: List[Dict[str, Any]]
    graph_evidence: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]]
    # 追踪
    _trace_rule_score: int
    _trace_graph_score: int
    _trace_blend: int
    _trace_combo_rank: int


def build_matching_subgraph(kb_url: str = "http://localhost:8004"):
    """编译 matching 子图: rule_score ∥ graph_score → blend → combo_rank.

    使用 Send() 声明两个评分节点并行执行, LangGraph 自动管理并发调度.
    """
    try:
        from langgraph.graph import StateGraph, END, START
        from langgraph.types import Send
    except ImportError:
        logger.warning("langgraph not installed, subgraph unavailable")
        return None

    _configure_kb_url(kb_url)

    try:
        subgraph = StateGraph(MatchSubgraphState)

        subgraph.add_node("rule_score", _rule_score_node)
        subgraph.add_node("graph_score", _graph_score_node)
        subgraph.add_node("blend", _blend_node)
        subgraph.add_node("combo_rank", _combo_rank_node)

        # Send() 并行扇出 — rule_score ∥ graph_score
        def fan_out_rule_graph(state: Dict[str, Any]):
            return [Send("rule_score", state), Send("graph_score", state)]

        subgraph.add_conditional_edges(START, fan_out_rule_graph,
                                        path_map={"rule_score": "rule_score",
                                                  "graph_score": "graph_score"})

        # 两个并行分支汇聚到 blend
        subgraph.add_edge("rule_score", "blend")
        subgraph.add_edge("graph_score", "blend")
        subgraph.add_edge("blend", "combo_rank")
        subgraph.add_edge("combo_rank", END)

        compiled = subgraph.compile()
        logger.info("Matching subgraph compiled (rule_score ∥ graph_score → blend → combo_rank)")
        return compiled
    except Exception as e:
        logger.error(f"Failed to build matching subgraph: {e}")
        return None
