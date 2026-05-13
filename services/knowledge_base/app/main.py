import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .json_repository import JsonRepository
from .json_repository import FEEDBACK_PATH  # noqa: F401 — 测试兼容
from .graph_repository import GraphRepository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("knowledge-base")

# ── 后端选择 ─────────────────────────────────────────────────
# KNOWLEDGE_BACKEND: "json" (默认) | "neo4j" | "auto"
#   - json:  始终使用 JSON 文件
#   - neo4j: 始终使用 Neo4j, 不可用时返回 503
#   - auto:  优先 Neo4j, 不可用自动 fallback 到 JSON
BACKEND = os.getenv("KNOWLEDGE_BACKEND", "json").strip().lower()


def _prefer_graph() -> bool:
    """根据 BACKEND 配置判断是否优先尝试 Neo4j."""
    return BACKEND in ("neo4j", "auto")


def _require_graph() -> bool:
    """标记 Neo4j 为强制 (不可用时报错)."""
    return BACKEND == "neo4j"


def _repo(method_name: str, *args, **kwargs):
    """统一调度: 根据 BACKEND 决定调用 GraphRepository 或 JsonRepository.

    返回 Optional[T] — 当 Neo4j 失败且 BACKEND=neo4j 时抛异常,
    否则 fallback 到 JSON.
    """
    if _prefer_graph():
        result = getattr(GraphRepository, method_name)(*args, **kwargs)
        if result is not None:
            return result
        if _require_graph():
            raise RuntimeError(f"Neo4j is required (KNOWLEDGE_BACKEND=neo4j) but unavailable")
        logger.info(f"Neo4j {method_name} returned None, falling back to JSON")
    return getattr(JsonRepository, method_name)(*args, **kwargs)


app = FastAPI(title="Knowledge Base Service", version="0.2.0")


class StylePayload(BaseModel):
    name: str
    tags: list[str]
    best_for: list[str]
    pros: list[str]
    cons: list[str]


class FeedbackPayload(BaseModel):
    requirement: str
    recommended_style: str
    user_choice: Optional[str] = None
    comment: Optional[str] = None


# ── 保持向后兼容的模块级函数 ──────────────────────────────────
# 测试和 matching-agent 可能直接 import 这些函数


def load_styles() -> Dict[str, Any]:
    """兼容旧 import, 始终从 JSON 读取."""
    return JsonRepository.get_styles()


def add_style(payload) -> Dict[str, Any]:
    """兼容旧 import, 直接写入 JSON."""
    count = JsonRepository.add_style(payload.model_dump() if hasattr(payload, 'model_dump') else payload)
    return {"status": "ok", "count": count}


def save_styles(data: Dict[str, Any]) -> None:
    """兼容旧 import, 直接写入 JSON."""
    import json
    from .json_repository import STYLES_PATH
    with open(STYLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_feedback(payload) -> Dict[str, Any]:
    """兼容旧 import, 直接写入 JSON."""
    return JsonRepository.add_feedback(
        requirement=payload.requirement,
        recommended_style=payload.recommended_style,
        user_choice=payload.user_choice,
        comment=payload.comment,
    )


def get_feedback_stats() -> Dict[str, Any]:
    """兼容旧 import, 从 JSON 读取."""
    return JsonRepository.get_feedback_stats()


# ── API 端点 ──────────────────────────────────────────────────


@app.get("/health")
def health() -> Dict[str, Any]:
    backend_info = _repo("graph_status") if _prefer_graph() else {"backend": "json"}
    return {
        "status": "ok",
        "service": "knowledge-base",
        "backend": BACKEND,
        "neo4j_available": backend_info.get("neo4j_available", False),
    }


@app.get("/styles")
def get_styles() -> Dict[str, Any]:
    return _repo("get_styles")


@app.post("/styles")
def add_style_endpoint(payload: StylePayload) -> Dict[str, Any]:
    count = _repo("add_style", payload.model_dump())
    return {"status": "ok", "count": count}


@app.get("/feedback")
def get_feedback() -> Dict[str, Any]:
    return _repo("get_feedback")


@app.post("/feedback")
def add_feedback_endpoint(payload: FeedbackPayload) -> Dict[str, Any]:
    return _repo("add_feedback",
                 payload.requirement, payload.recommended_style,
                 payload.user_choice, payload.comment)


@app.get("/feedback/stats")
def feedback_stats() -> Dict[str, Any]:
    return _repo("get_feedback_stats")


@app.get("/feedback/weights")
def get_learned_weights() -> Dict[str, Any]:
    return _repo("get_learned_weights")


class GraphMatchRequest(BaseModel):
    features: Dict[str, bool]


@app.get("/graph/status")
def graph_status() -> Dict[str, Any]:
    """返回知识库后端状态: 当前使用的 backend, Neo4j 是否可用, 节点/关系数量."""
    if _prefer_graph():
        status = GraphRepository.graph_status()
    else:
        status = JsonRepository.graph_status()
    status["configured_backend"] = BACKEND
    return status


@app.post("/graph/match")
def graph_match(payload: GraphMatchRequest) -> Dict[str, Any]:
    """图谱关系匹配: 根据特征查找匹配的架构风格及关联证据.

    Neo4j 不可用时返回 available=false, matching-agent 应回退到规则引擎.
    """
    if not _prefer_graph():
        return {"available": False, "reason": "Graph backend not enabled (KNOWLEDGE_BACKEND=json)"}
    result = GraphRepository.graph_match(payload.features)
    if result is None:
        return {"available": False, "reason": "Neo4j unavailable or no matches"}
    return result


# ── ADR (Architecture Decision Record) 端点 ───────────────────

class ADRPayload(BaseModel):
    requirement: str
    extracted_features: Dict[str, bool]
    candidates: List[Dict[str, Any]]
    recommended_style: str
    recommended_style_zh: str = ""
    alternative_styles: List[str] = []
    decision_basis: Dict[str, Any] = {}
    risk_and_suggestions: Dict[str, Any] = {}
    graph_evidence: Dict[str, Any] = {}
    workflow_engine: str = "manual"


@app.post("/adr")
def create_adr(payload: ADRPayload) -> Dict[str, Any]:
    """保存一次架构决策记录."""
    adr_data = payload.model_dump()
    adr_data["timestamp"] = datetime.now().isoformat(timespec="seconds")
    return _repo("add_adr", adr_data)


@app.get("/adr")
def list_adrs(limit: int = 20) -> Dict[str, Any]:
    """列出最近的 ADR."""
    return _repo("get_adrs", limit)


@app.get("/combinations")
def get_combinations() -> Dict[str, Any]:
    """返回架构组合模式列表."""
    return _repo("get_combinations")


@app.get("/adr/{adr_id}")
def get_adr(adr_id: str) -> Dict[str, Any]:
    """查看单条 ADR."""
    result = _repo("get_adr", adr_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"ADR {adr_id} not found")
    return result
