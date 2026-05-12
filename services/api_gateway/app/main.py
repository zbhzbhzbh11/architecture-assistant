import os
import time
import logging
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api-gateway")

app = FastAPI(title="API Gateway", version="0.1.0")

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


class RecommendRequest(BaseModel):
    requirement: str = Field(..., min_length=10, description="Natural language requirement text")


class RecommendResponse(BaseModel):
    extracted_features: Dict[str, Any]
    feature_hits: Dict[str, Any]
    candidates: list[Dict[str, Any]]
    final_report: Dict[str, Any]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "api-gateway"}


@app.post("/api/v1/recommend", response_model=RecommendResponse)
async def recommend(payload: RecommendRequest) -> RecommendResponse:
    t_total_start = time.perf_counter()
    logger.info(f"Received recommendation request: {payload.requirement[:50]}...")
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            # 1. Extract features
            t0 = time.perf_counter()
            logger.info("Calling requirements-agent/extract...")
            req_resp = await client.post(
                f"{REQUIREMENTS_AGENT_URL}/extract",
                json={"requirement": payload.requirement},
            )
            req_resp.raise_for_status()
            extracted = req_resp.json()
            logger.info(f"requirements-agent responded in {(time.perf_counter()-t0)*1000:.0f}ms")

            # 2. Match styles
            t0 = time.perf_counter()
            logger.info("Calling matching-agent/match...")
            match_resp = await client.post(
                f"{MATCHING_AGENT_URL}/match",
                json={"features": extracted["features"]},
            )
            match_resp.raise_for_status()
            matching = match_resp.json()
            logger.info(f"matching-agent responded in {(time.perf_counter()-t0)*1000:.0f}ms")

            # 3. Evaluate results
            t0 = time.perf_counter()
            logger.info("Calling evaluation-agent/evaluate...")
            eval_resp = await client.post(
                f"{EVALUATION_AGENT_URL}/evaluate",
                json={
                    "requirement": payload.requirement,
                    "features": extracted["features"],
                    "candidates": matching["candidates"],
                },
            )
            eval_resp.raise_for_status()
            final_report = eval_resp.json()
            logger.info(f"evaluation-agent responded in {(time.perf_counter()-t0)*1000:.0f}ms")

            t_total = (time.perf_counter() - t_total_start) * 1000
            logger.info(f"Recommendation successful: {final_report.get('recommended_style')} (total {t_total:.0f}ms)")
        except httpx.HTTPError as exc:
            logger.error(f"Upstream service error: {exc}")
            raise HTTPException(status_code=502, detail=f"Upstream service error: {exc}") from exc
        except Exception as exc:
            logger.error(f"Unexpected error: {exc}")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    return RecommendResponse(
        extracted_features=extracted["features"],
        feature_hits=extracted.get("feature_hits", {}),
        candidates=matching["candidates"],
        final_report=final_report,
    )
