"""Matching Subgraph — 规则引擎评分 + Neo4j 数据源.

规则引擎从 Neo4j 拉取风格/权重数据, 执行四层确定性评分,
select_top3 选出 Top 3 候选, 最后做组合推荐.

【子图拓扑】
  START → rule_score → top3_select → combo_rank → END
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
# 子节点
# ═══════════════════════════════════════════════════════════════


async def _rule_score_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 1: 从 knowledge-base (Neo4j 权威源) 拉取 styles + weights, 逐风格评分."""
    t0 = time.perf_counter()
    features = state.get("features", {})
    logger.info("[subgraph] rule_score: fetching styles from Neo4j...")

    async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
        resp = await client.get(f"{KNOWLEDGE_BASE_URL}/styles")
        resp.raise_for_status()
        styles = resp.json()["styles"]

        learned_weights: Dict[str, Dict[str, int]] = {}
        raw_weights: Dict[str, Dict[str, float]] = {}
        try:
            lw_resp = await client.get(f"{KNOWLEDGE_BASE_URL}/feedback/weights")
            lw_resp.raise_for_status()
            lw_data = lw_resp.json()
            learned_weights = lw_data.get("weights", {})
            raw_weights = lw_data.get("raw_weights", {})
        except Exception:
            pass

    llm_disputed = state.get("llm_disputed", {})
    scored = [score_style(s, features, learned_weights, llm_disputed, raw_weights) for s in styles]

    elapsed = round((time.perf_counter() - t0) * 1000)
    top_scores = sorted(scored, key=lambda x: x["score"], reverse=True)[:3]
    logger.info(f"[subgraph] rule_score done: top3={[(c['style'], c['score']) for c in top_scores]}, {elapsed}ms")
    return {"rule_scored": scored, "_trace_rule_score": elapsed}


async def _top3_select_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 2: 排序 + Top 3 选择. 同时从图谱获取风险/场景/组合证据."""
    t0 = time.perf_counter()
    rule_scored = state.get("rule_scored", [])
    features = state.get("features", {})

    rule_scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = select_top3(rule_scored)

    # 从图谱获取证据 (风险/场景/组合) — 用于前端展示, 不参与评分
    graph_evidence: Dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            for c in candidates:
                style_name = c["style"]
                try:
                    resp = await client.get(
                        f"{KNOWLEDGE_BASE_URL}/graph/risks/{style_name}"
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        c.setdefault("related_risks", data.get("main_risks", []))
                        c.setdefault("matched_attributes", [
                            tag for tag in c.get("reasons", [])
                            if "特征匹配" in tag or "图谱:" in tag
                        ])
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[subgraph] Graph evidence fetch failed (non-fatal): {e}")

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] top3_select done: {[c['style'] for c in candidates]}, {elapsed}ms")
    return {
        "blended": rule_scored,
        "candidates": candidates,
        "graph_evidence": graph_evidence,
        "_trace_top3_select": elapsed,
    }


async def _combo_rank_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 3: 组合推荐 — 动态发现 (Neo4j COMPLEMENTS) + JSON fallback."""
    t0 = time.perf_counter()
    candidates = state.get("candidates", [])
    blended = state.get("blended", [])
    features = state.get("features", {})

    combo_candidates: List[Dict[str, Any]] = []
    candidate_names = [c["style"] for c in candidates]

    # 1. 从 Neo4j COMPLEMENTS 动态发现组合
    dynamic_combos: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            # 查询 Top3 候选之间的 COMPLEMENTS 关系
            resp = await client.post(
                f"{KNOWLEDGE_BASE_URL}/graph/match",
                json={"features": features},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("available"):
                    # 从图谱评分结果中提取 combinable_styles
                    graph_scored = data.get("scored", [])
                    for gs in graph_scored:
                        style_name = gs.get("style", "")
                        if style_name in candidate_names:
                            for combo_style in gs.get("combinable_styles", []):
                                if combo_style in candidate_names and style_name < combo_style:
                                    dynamic_combos.append({
                                        "name": f"{style_name} + {combo_style}",
                                        "name_zh": next((c.get("style_zh", c["style"])
                                            for c in candidates if c["style"] == style_name), style_name)
                                            + " + " + next((c.get("style_zh", c["style"])
                                            for c in candidates if c["style"] == combo_style), combo_style),
                                        "styles": [style_name, combo_style],
                                        "tags": features.keys(),
                                        "best_for": [], "best_for_zh": [],
                                        "synergy": "COMPLEMENTS 关系确认的组合",
                                        "synergy_zh": f"图谱确认: {style_name} 与 {combo_style} 可互补组合",
                                        "complexity_penalty": 1,
                                        "topology_mermaid": "",
                                    })
    except Exception as e:
        logger.warning(f"[subgraph] Dynamic combo discovery failed: {e}")

    # 2. JSON 预定义组合 (补充协同描述/拓扑图)
    json_combos: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{KNOWLEDGE_BASE_URL}/combinations")
            resp.raise_for_status()
            json_combos = resp.json().get("combinations", [])
    except Exception as e:
        logger.warning(f"[subgraph] JSON combo fetch failed: {e}")

    # 3. 合并: 动态组合优先, JSON 补充 (去重)
    all_combos = dynamic_combos.copy()
    seen_pairs = {tuple(sorted(c["styles"])) for c in dynamic_combos}
    for jc in json_combos:
        jc_pair = tuple(sorted(jc.get("styles", [])))
        if jc_pair not in seen_pairs:
            all_combos.append(jc)
            seen_pairs.add(jc_pair)

    if all_combos:
        scored_by_name = {item["style"]: item for item in blended}
        combo_candidates = rank_combinations(
            all_combos, scored_by_name, features, {}, top_n=3,
        )

    elapsed = round((time.perf_counter() - t0) * 1000)
    combo_detail = []
    for cc in combo_candidates[:3]:
        combo_detail.append(f"{cc.get('combination_name_zh', cc.get('combination_name', '?'))}={cc.get('combo_score', 0)}")
    logger.info(f"[subgraph] combo_rank done: {combo_detail} (dynamic={len(dynamic_combos)}, json={len(json_combos)}), {elapsed}ms")
    return {"combination_candidates": combo_candidates, "_trace_combo_rank": elapsed}


# ═══════════════════════════════════════════════════════════════
# 子图状态 + 工厂
# ═══════════════════════════════════════════════════════════════


class MatchSubgraphState(TypedDict, total=False):
    """TypedDict 各字段为独立 channel."""
    features: Dict[str, bool]
    llm_disputed: Dict[str, bool]
    arch_inclination: Dict[str, Any]
    rule_scored: List[Dict[str, Any]]
    blended: List[Dict[str, Any]]
    graph_evidence: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]]
    _trace_rule_score: int
    _trace_top3_select: int
    _trace_combo_rank: int


def build_matching_subgraph(kb_url: str = "http://localhost:8004"):
    """编译 matching 子图: rule_score → top3_select → combo_rank."""
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        logger.warning("langgraph not installed, subgraph unavailable")
        return None

    _configure_kb_url(kb_url)

    try:
        subgraph = StateGraph(MatchSubgraphState)

        subgraph.add_node("rule_score", _rule_score_node)
        subgraph.add_node("top3_select", _top3_select_node)
        subgraph.add_node("combo_rank", _combo_rank_node)

        subgraph.add_edge(START, "rule_score")
        subgraph.add_edge("rule_score", "top3_select")
        subgraph.add_edge("top3_select", "combo_rank")
        subgraph.add_edge("combo_rank", END)

        compiled = subgraph.compile()
        logger.info("Matching subgraph compiled (rule_score → top3_select → combo_rank)")
        return compiled
    except Exception as e:
        logger.error(f"Failed to build matching subgraph: {e}")
        return None
