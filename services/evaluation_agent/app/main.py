"""Evaluation Agent — LangGraph Subgraph with Send() parallel fan-out.

评估流程由 4 子节点 Subgraph 驱动:
  sort → Send(vote ∥ summary) → merge

Send() 声明 vote 和 summary 两个 LLM 调用并行执行,
替代原来的 asyncio.gather 手动并行.
"""

import json
import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

_SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

_ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _ENV_PATH.exists():
    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _key, _, _val = _line.partition("=")
                    if _key.strip() and _val.strip() and _key.strip() not in os.environ:
                        os.environ[_key.strip()] = _val.strip()
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluation-agent")

app = FastAPI(title="Evaluation Agent", version="0.3.0")

LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "http://localhost:8004").strip()

from .evaluation_subgraph import build_evaluation_subgraph
from .evaluation_subgraph import (
    _localize_reasons, _dynamic_risks, _fallback_summary,
    llm_vote_style, llm_summary,
)

# 惰性初始化
_eval_subgraph = None

class EvaluateRequest(BaseModel):
    requirement: str
    features: Dict[str, bool]
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]] = []


def _get_subgraph():
    global _eval_subgraph
    if _eval_subgraph is None:
        from . import evaluation_subgraph as esub
        esub.LLM_API_BASE = LLM_API_BASE
        esub.LLM_API_KEY = LLM_API_KEY
        esub.LLM_MODEL = LLM_MODEL
        esub.KNOWLEDGE_BASE_URL = KNOWLEDGE_BASE_URL
        _eval_subgraph = build_evaluation_subgraph(
            LLM_API_BASE, LLM_API_KEY, LLM_MODEL, KNOWLEDGE_BASE_URL)
    return _eval_subgraph


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "evaluation-agent"}


@app.post("/evaluate")
async def evaluate(payload: EvaluateRequest) -> Dict[str, Any]:
    subgraph = _get_subgraph()
    return await _eval_via_subgraph(payload, subgraph)


async def _eval_via_subgraph(payload: EvaluateRequest, subgraph) -> Dict[str, Any]:
    """Subgraph 路径: sort → Send(vote ∥ summary) → merge."""
    initial_state: Dict[str, Any] = {
        "requirement": payload.requirement,
        "features": payload.features,
        "candidates": payload.candidates,
        "combination_candidates": payload.combination_candidates,
    }
    result = await subgraph.ainvoke(initial_state)
    return result.get("final_report", {})
