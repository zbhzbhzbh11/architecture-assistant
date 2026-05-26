"""Matching Agent — 双驱动并行架构 (规则引擎 + 图谱引擎).

匹配流程由 4 子节点 Subgraph 驱动:
  START → Send(rule_score ∥ graph_score) → blend → combo_rank → END

纯评分函数 (score_style, rank_combinations) 从
common.matching 导入, Subgraph 节点和 HTTP 端点共用同一套逻辑.
"""

import os
import logging
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.matching import score_style, select_top3, rank_combinations
from .combo_matcher import fetch_combinations
from .matching_subgraph import build_matching_subgraph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("matching-agent")

app = FastAPI(title="Matching Agent", version="0.4.0")
KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "http://localhost:8004")

class MatchRequest(BaseModel):
    features: Dict[str, bool]
    llm_disputed: Dict[str, bool] = {}
    arch_inclination: Dict[str, Any] = {}

class MatchResponse(BaseModel):
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]] = []


def _get_subgraph():
    """每次请求重新编译 Subgraph, 避免 Python 模块缓存导致的代码不同步."""
    return build_matching_subgraph(KNOWLEDGE_BASE_URL)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "matching-agent"}


@app.post("/match", response_model=MatchResponse)
async def match(payload: MatchRequest) -> MatchResponse:
    """POST /match — 特征向量 → Top 3 候选 + 组合推荐."""
    subgraph = _get_subgraph()
    if subgraph is not None:
        return await _match_via_subgraph(payload, subgraph)
    return await _match_direct(payload)


async def _match_via_subgraph(payload: MatchRequest, subgraph) -> MatchResponse:
    """Subgraph 路径: StateGraph 执行."""
    initial_state: Dict[str, Any] = {
        "features": payload.features,
        "llm_disputed": payload.llm_disputed,
        "arch_inclination": payload.arch_inclination,
    }
    result = await subgraph.ainvoke(initial_state)
    return MatchResponse(
        candidates=result.get("candidates", []),
        combination_candidates=result.get("combination_candidates", []),
    )


async def _match_direct(payload: MatchRequest) -> MatchResponse:
    """直落路径: asyncio.gather 并行 (langgraph 不可用时)."""
    import asyncio
    from .matching_subgraph import _rule_score_node, _graph_score_node, _blend_node, _combo_rank_node

    state: Dict[str, Any] = {
        "features": payload.features,
        "llm_disputed": payload.llm_disputed,
        "arch_inclination": payload.arch_inclination,
    }

    # 并行执行规则评分 + 图谱评分 (asyncio.gather 替代 Send())
    rule_result, graph_result = await asyncio.gather(
        _rule_score_node(state),
        _graph_score_node(state),
    )
    state.update(rule_result)
    state.update(graph_result)

    # 融合 + 组合推荐
    blend_result = await _blend_node(state)
    state.update(blend_result)
    combo_result = await _combo_rank_node(state)
    state.update(combo_result)

    return MatchResponse(
        candidates=state.get("candidates", []),
        combination_candidates=state.get("combination_candidates", []),
    )
