"""Matching Agent — 规则引擎评分 + Neo4j 知识图谱数据源.

匹配流程由 3 子节点 Subgraph 驱动:
  rule_score → top3_select → combo_rank

规则引擎从 Neo4j 读取风格/权重数据, 执行四层确定性评分.
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
