import os
import logging
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("matching-agent")

app = FastAPI(title="Matching Agent", version="0.1.0")
KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "http://localhost:8004")


class MatchRequest(BaseModel):
    features: Dict[str, bool]


class MatchResponse(BaseModel):
    candidates: List[Dict[str, Any]]


MAINSTREAM_STYLES = [
    "Layered Architecture",
    "Microservices",
    "Event-Driven Architecture",
]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "matching-agent"}


def score_style(style: Dict[str, Any], features: Dict[str, bool],
                learned_weights: Dict[str, Dict[str, int]] | None = None) -> Dict[str, Any]:
    score = 0
    hit_reasons: List[str] = []

    for tag in style.get("tags", []):
        if features.get(tag):
            score += 2
            hit_reasons.append(f"matches feature: {tag}")

    # 知识进化：基于历史反馈的学习权重加分（跨特征，不局限风格已有标签）
    if learned_weights:
        style_name = style["name"]
        for feat, is_active in features.items():
            if is_active and feat in learned_weights:
                w = learned_weights[feat].get(style_name, 0)
                if w >= 2:  # 至少 2 次确认才加分
                    score += 1
                    hit_reasons.append(f"learned boost: {feat}->{style_name} (confirmed {w}x)")

    if style["name"] == "Event-Driven Architecture" and features.get("high_concurrency"):
        score += 1
        hit_reasons.append("extra rule: high concurrency favors event-driven")

    if style["name"] == "Microservices" and features.get("team_size_large"):
        score += 1
        hit_reasons.append("extra rule: multi-team delivery favors microservices")

    if style["name"] == "Layered Architecture" and features.get("strict_consistency"):
        score += 1
        hit_reasons.append("extra rule: strict consistency fits layered core domain")

    if style["name"] == "Pipeline-Filter" and features.get("data_intensive") and features.get("real_time"):
        score += 1
        hit_reasons.append("extra rule: real-time stream processing favors pipeline-filter")

    if style["name"] == "CQRS" and features.get("data_intensive") and features.get("high_concurrency"):
        score += 1
        hit_reasons.append("extra rule: high-concurrency data access favors CQRS")

    if style["name"] == "Microservices" and features.get("high_concurrency") and features.get("strict_consistency"):
        score += 1
        hit_reasons.append("extra rule: high-concurrency with strict consistency favors microservices")

    return {
        "style": style["name"],
        "style_zh": style.get("name_zh", style["name"]),
        "score": score,
        "reasons": hit_reasons,
        "pros": style.get("pros", []),
        "pros_zh": style.get("pros_zh", []),
        "cons": style.get("cons", []),
        "cons_zh": style.get("cons_zh", []),
        "best_for": style.get("best_for", []),
        "best_for_zh": style.get("best_for_zh", []),
        "topology_mermaid": style.get("topology_mermaid", ""),
    }


@app.post("/match", response_model=MatchResponse)
async def match(payload: MatchRequest) -> MatchResponse:
    async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
        try:
            kb_resp = await client.get(f"{KNOWLEDGE_BASE_URL}/styles")
            kb_resp.raise_for_status()
            styles = kb_resp.json()["styles"]
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Knowledge-base unavailable: {exc}") from exc

        # 知识进化：从 knowledge-base 拉取用户反馈积累的学习权重
        # 权重结构: {feature: {style: count}} —— 用于 score_style 的 learned boost
        learned_weights = {}
        try:
            lw_resp = await client.get(f"{KNOWLEDGE_BASE_URL}/feedback/weights")
            lw_resp.raise_for_status()
            learned_weights = lw_resp.json().get("weights", {})
        except Exception:
            pass  # 权重服务不可用时降级——不影响核心规则评分链路

    scored = [score_style(s, payload.features, learned_weights) for s in styles]
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Prefer mainstream styles in candidate set to satisfy course requirement.
    by_name = {item["style"]: item for item in scored}
    mainstream_ranked = [by_name[name] for name in MAINSTREAM_STYLES if name in by_name]
    non_mainstream = [item for item in scored if item["style"] not in MAINSTREAM_STYLES]

    # If no signals are extracted, return mainstream styles as baseline comparison set.
    if all(item["score"] == 0 for item in mainstream_ranked):
        top3 = mainstream_ranked[:3]
    else:
        top3 = []
        for item in mainstream_ranked:
            if item["score"] > 0 and len(top3) < 3:
                top3.append(item)
        for item in scored:
            if item["style"] not in {x["style"] for x in top3} and len(top3) < 3:
                top3.append(item)

        if len(top3) < 3:
            for item in non_mainstream:
                if item["style"] not in {x["style"] for x in top3} and len(top3) < 3:
                    top3.append(item)

    return MatchResponse(candidates=top3)
