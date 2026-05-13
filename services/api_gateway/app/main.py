import os
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── 本地开发: services/ → sys.path ──
_SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

from .langchain_workflow import build_workflow
from .workflow_state import ArchitectureWorkflowState

# ── 缓存后端选择 ──────────────────────────────────────────────
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory").strip().lower()
if CACHE_BACKEND == "sqlite":
    from common.cache.sqlite_cache import get as cache_get, set as cache_set, clear as cache_clear, stats as cache_stats
else:
    from common.cache.simple_cache import get as cache_get, set as cache_set, clear as cache_clear, stats as cache_stats

from common.cache.hash_utils import cache_key, knowledge_version

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api-gateway")

app = FastAPI(title="API Gateway", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REQUIREMENTS_AGENT_URL = os.getenv("REQUIREMENTS_AGENT_URL", "http://localhost:8001")
MATCHING_AGENT_URL = os.getenv("MATCHING_AGENT_URL", "http://localhost:8002")
EVALUATION_AGENT_URL = os.getenv("EVALUATION_AGENT_URL", "http://localhost:8003")
REFACTORING_AGENT_URL = os.getenv("REFACTORING_AGENT_URL", "http://localhost:8005")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

# ── LangGraph 工作流初始化 ───────────────────────────────────
_langgraph_app = build_workflow(
    req_url=REQUIREMENTS_AGENT_URL,
    match_url=MATCHING_AGENT_URL,
    eval_url=EVALUATION_AGENT_URL,
)
WORKFLOW_ENGINE = "langgraph" if _langgraph_app is not None else "manual"
logger.info(f"API Gateway workflow engine: {WORKFLOW_ENGINE}")
logger.info(f"Cache backend: {CACHE_BACKEND}, kv={knowledge_version()}")


class RecommendRequest(BaseModel):
    requirement: str = Field(..., min_length=10, description="Natural language requirement text")


class RecommendResponse(BaseModel):
    extracted_features: Dict[str, Any]
    feature_hits: Dict[str, Any]
    candidates: list[Dict[str, Any]]
    final_report: Dict[str, Any]
    workflow_engine: str = "manual"
    workflow_trace: List[Dict[str, Any]] = []
    cache_hit: bool = False


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "api-gateway",
        "workflow_engine": WORKFLOW_ENGINE,
        "cache_backend": CACHE_BACKEND,
    }


async def _manual_orchestrate(payload: RecommendRequest) -> Dict[str, Any]:
    """手写编排 fallback — 保留原有三步串行逻辑."""
    trace: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        t0 = time.perf_counter()
        logger.info("Calling requirements-agent/extract...")
        req_resp = await client.post(
            f"{REQUIREMENTS_AGENT_URL}/extract",
            json={"requirement": payload.requirement},
        )
        req_resp.raise_for_status()
        extracted = req_resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        trace.append({"node": "extract", "elapsed_ms": elapsed, "status": "ok"})
        logger.info(f"requirements-agent responded in {elapsed}ms")

        t0 = time.perf_counter()
        logger.info("Calling matching-agent/match...")
        match_resp = await client.post(
            f"{MATCHING_AGENT_URL}/match",
            json={"features": extracted["features"]},
        )
        match_resp.raise_for_status()
        matching = match_resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        trace.append({"node": "match", "elapsed_ms": elapsed, "status": "ok"})
        logger.info(f"matching-agent responded in {elapsed}ms")

        t0 = time.perf_counter()
        logger.info("Calling evaluation-agent/evaluate...")
        eval_resp = await client.post(
            f"{EVALUATION_AGENT_URL}/evaluate",
            json={
                "requirement": payload.requirement,
                "features": extracted["features"],
                "candidates": matching["candidates"],
                "combination_candidates": matching.get("combination_candidates", []),
            },
        )
        eval_resp.raise_for_status()
        final_report = eval_resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        trace.append({"node": "evaluate", "elapsed_ms": elapsed, "status": "ok"})
        logger.info(f"evaluation-agent responded in {elapsed}ms")

    return {
        "extracted_features": extracted["features"],
        "feature_hits": extracted.get("feature_hits", {}),
        "candidates": matching["candidates"],
        "final_report": final_report,
        "workflow_engine": "manual",
        "workflow_trace": trace,
    }

# ── 组合匹配在 matching-agent 完成，此处无需额外处理 ──

async def _langgraph_orchestrate(payload: RecommendRequest) -> Dict[str, Any]:
    """LangGraph 状态图编排."""
    initial_state: ArchitectureWorkflowState = {
        "requirement": payload.requirement,
        "extracted_features": {},
        "feature_hits": {},
        "candidates": [],
        "final_report": {},
        "errors": [],
        "trace": [],
    }
    result = await _langgraph_app.ainvoke(initial_state)
    return {
        "extracted_features": result.get("extracted_features", {}),
        "feature_hits": result.get("feature_hits", {}),
        "candidates": result.get("candidates", []),
        "final_report": result.get("final_report", {}),
        "workflow_engine": "langgraph",
        "workflow_trace": result.get("trace", []),
    }


@app.post("/api/v1/recommend")
async def recommend(payload: RecommendRequest) -> Dict[str, Any]:
    t_total_start = time.perf_counter()
    logger.info(f"Received recommendation request: {payload.requirement[:50]}...")

    # ── 请求级缓存 ──
    key = cache_key(payload.requirement, LLM_MODEL)
    cached = cache_get(key)
    if cached is not None:
        t_total = round((time.perf_counter() - t_total_start) * 1000)
        logger.info(f"Cache HIT for key={key} (total {t_total}ms)")
        cached["cache_hit"] = True
        return cached

    # ── 编排执行 ──
    if _langgraph_app is not None:
        try:
            result = await _langgraph_orchestrate(payload)
        except Exception as exc:
            logger.error(f"LangGraph workflow failed, falling back to manual: {exc}")
            result = await _manual_orchestrate(payload)
    else:
        result = await _manual_orchestrate(payload)

    result["cache_hit"] = False

    # ── 重构建议 (失败不阻塞主链路) ──
    refactoring_advice = {}
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as ref_client:
            ref_resp = await ref_client.post(
                f"{REFACTORING_AGENT_URL}/refactor",
                json={
                    "requirement": payload.requirement,
                    "features": result.get("extracted_features", {}),
                    "candidates": result.get("candidates", []),
                    "recommended_style": result["final_report"].get("recommended_style", ""),
                    "recommended_combination": result["final_report"].get("recommended_combination", {}),
                },
            )
            if ref_resp.status_code == 200:
                refactoring_advice = ref_resp.json()
                logger.info(f"Refactoring advice: needed={refactoring_advice.get('refactoring_needed')}")
    except Exception as e:
        logger.warning(f"Refactoring agent unavailable (non-fatal): {e}")

    result["final_report"]["refactoring_advice"] = refactoring_advice
    cache_set(key, result)

    t_total = round((time.perf_counter() - t_total_start) * 1000)
    logger.info(
        f"Recommendation successful: {result['final_report'].get('recommended_style')} "
        f"(engine={result['workflow_engine']}, cache=miss, total {t_total}ms)"
    )
    return result


# ── 缓存管理端点 ──────────────────────────────────────────────

@app.get("/cache/stats")
def get_cache_stats() -> Dict[str, Any]:
    stats = cache_stats()
    stats["knowledge_version"] = knowledge_version()
    return stats


@app.post("/cache/clear")
def clear_cache() -> Dict[str, Any]:
    count = cache_clear()
    return {"status": "ok", "cleared": count}
