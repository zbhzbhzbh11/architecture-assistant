"""Knowledge Base Service — 知识存储层端点定义 + 双后端调度.

【模块功能】
提供 10 种架构风格的 CRUD、用户反馈收集、ADR 存储、图谱查询、
架构组合列表、学习权重计算等 REST API。

【双后端调度 — _repo()】
所有端点通过 _repo() 统一调度到 Neo4j 或 JSON 存储:
  BACKEND=json  → 始终使用 JsonRepository (零外部依赖)
  BACKEND=neo4j → 始终使用 Neo4j (不可用时报错)
  BACKEND=auto  → 优先 Neo4j, 不可用时自动 fallback JSON (默认)

【端点一览】
  GET  /styles            → 全部 10 种架构风格
  POST /styles            → 新增架构风格
  POST /feedback          → 提交用户反馈 + 即时权重重算
  GET  /feedback/weights  → 学习权重查询 (Neo4j 为权威源)
  POST /feedback/reset    → 清空所有反馈和权重
  GET  /graph/status      → Neo4j/JSON 后端状态
  POST /graph/match       → Cypher 图谱匹配
  POST /adr               → 创建架构决策记录
  GET  /adr               → ADR 列表
  GET  /combinations      → 架构组合模式列表
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .json_repository import JsonRepository
from .json_repository import FEEDBACK_PATH  # noqa: F401 — 测试兼容
from .graph_repository import GraphRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("knowledge-base")

# ═══════════════════════════════════════════════════════════════
# 后端选择 — 环境变量 KNOWLEDGE_BACKEND 控制
# ═══════════════════════════════════════════════════════════════
BACKEND = os.getenv("KNOWLEDGE_BACKEND", "json").strip().lower()


def _prefer_graph() -> bool:
    return BACKEND in ("neo4j", "auto")


def _require_graph() -> bool:
    return BACKEND == "neo4j"


def _repo(method_name: str, *args, **kwargs):
    """统一调度: 根据 BACKEND 决定调用 GraphRepository 或 JsonRepository.

    当 Graph 路径返回非 None 时直接返回;
    当 Graph 路径返回 None 且 require_graph 时抛 RuntimeError;
    其他情况 fallback 到 JsonRepository.
    """
    if _prefer_graph():
        result = getattr(GraphRepository, method_name)(*args, **kwargs)
        if result is not None:
            return result
        if _require_graph():
            raise RuntimeError(f"Neo4j is required (KNOWLEDGE_BACKEND=neo4j) but unavailable")
        logger.info(f"Neo4j {method_name} returned None, falling back to JSON")
    return getattr(JsonRepository, method_name)(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════
# FastAPI 应用 + CORS (前端 localhost:3000 可跨域调用)
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="Knowledge Base Service", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# Pydantic 请求模型
# ═══════════════════════════════════════════════════════════════

class StylePayload(BaseModel):
    name: str
    tags: list[str] = []
    best_for: list[str] = []
    best_for_zh: list[str] = []
    pros: list[str] = []
    pros_zh: list[str] = []
    cons: list[str] = []
    cons_zh: list[str] = []
    name_zh: str = ""
    topology_mermaid: str = ""
    penalty_tags: dict = {}


class FeedbackPayload(BaseModel):
    requirement: str
    recommended_style: str
    user_choice: Optional[str] = None
    comment: Optional[str] = None


# ── 模块级兼容函数 (测试和 matching-agent 可能直接 import) ──

def load_styles() -> Dict[str, Any]:
    return JsonRepository.get_styles()

def add_style(payload) -> Dict[str, Any]:
    count = JsonRepository.add_style(payload.model_dump() if hasattr(payload, 'model_dump') else payload)
    return {"status": "ok", "count": count}

def save_styles(data: Dict[str, Any]) -> None:
    import json
    from .json_repository import STYLES_PATH
    with open(STYLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_feedback(payload) -> Dict[str, Any]:
    return JsonRepository.add_feedback(
        requirement=payload.requirement,
        recommended_style=payload.recommended_style,
        user_choice=payload.user_choice,
        comment=payload.comment,
    )

def get_feedback_stats() -> Dict[str, Any]:
    return JsonRepository.get_feedback_stats()


# ═══════════════════════════════════════════════════════════════
# REST API 端点
# ═══════════════════════════════════════════════════════════════

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

@app.post("/feedback/reset")
def reset_learned_weights() -> Dict[str, Any]:
    """清空 Neo4j Feedback 节点 + learned_weights.json."""
    return _repo("reset_learned_weights")

class GraphMatchRequest(BaseModel):
    features: Dict[str, bool]

@app.get("/graph/status")
def graph_status() -> Dict[str, Any]:
    if _prefer_graph():
        status = GraphRepository.graph_status()
    else:
        status = JsonRepository.graph_status()
    status["configured_backend"] = BACKEND
    return status

@app.post("/graph/match")
def graph_match(payload: GraphMatchRequest) -> Dict[str, Any]:
    """Cypher 图谱匹配 — Neo4j 不可用时返回 available=false."""
    if not _prefer_graph():
        return {"available": False, "reason": "Graph backend not enabled (KNOWLEDGE_BACKEND=json)"}
    result = GraphRepository.graph_match(payload.features)
    if result is None:
        return {"available": False, "reason": "Neo4j unavailable or no matches"}
    return result

# ── ADR 端点 ──────────────────────────────────────────────

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
    adr_data = payload.model_dump()
    adr_data["timestamp"] = datetime.now().isoformat(timespec="seconds")
    return _repo("add_adr", adr_data)

@app.get("/adr")
def list_adrs(limit: int = 20) -> Dict[str, Any]:
    return _repo("get_adrs", limit)

@app.get("/combinations")
def get_combinations() -> Dict[str, Any]:
    return _repo("get_combinations")

@app.get("/adr/{adr_id}")
def get_adr(adr_id: str) -> Dict[str, Any]:
    result = _repo("get_adr", adr_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"ADR {adr_id} not found")
    return result


app = FastAPI(title="Knowledge Base Service", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StylePayload(BaseModel):
    name: str
    tags: list[str] = []
    best_for: list[str] = []
    best_for_zh: list[str] = []
    pros: list[str] = []
    pros_zh: list[str] = []
    cons: list[str] = []
    cons_zh: list[str] = []
    name_zh: str = ""
    topology_mermaid: str = ""
    penalty_tags: dict = {}


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


@app.post("/feedback/reset")
def reset_learned_weights() -> Dict[str, Any]:
    """重置学习权重 (清空 Neo4j Feedback 节点 + JSON 文件)."""
    return _repo("reset_learned_weights")


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
