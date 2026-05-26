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

# 启动时编译一次 Subgraph (模块级单例)
_matching_subgraph = None

class MatchRequest(BaseModel):
    features: Dict[str, bool]
    llm_disputed: Dict[str, bool] = {}
    arch_inclination: Dict[str, Any] = {}

class MatchResponse(BaseModel):
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]] = []


def _get_subgraph():
    """惰性初始化 Subgraph (首次调用时编译)."""
    global _matching_subgraph
    if _matching_subgraph is None:
        _matching_subgraph = build_matching_subgraph(KNOWLEDGE_BASE_URL)
    return _matching_subgraph


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "matching-agent"}


@app.post("/match", response_model=MatchResponse)
async def match(payload: MatchRequest) -> MatchResponse:
    """POST /match — 特征向量 → Top 3 候选 + 组合推荐.

    Subgraph 路径 (langgraph 可用):
      START → rule_score → graph_blend → combo_rank → END

    直落路径 (langgraph 不可用):
      顺序执行 规则评分 → 图谱融合 → Top3 → 组合推荐
    """
    subgraph = _get_subgraph()
    return await _match_via_subgraph(payload, subgraph)


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
