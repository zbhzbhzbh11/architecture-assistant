"""API Gateway - LangGraph StateGraph 编排 + 请求级缓存."""
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

# ═══════════════════════════════════════════════════════════════
# 路径设置: 本地开发时 services/ 挂到 sys.path
# Docker 中 WORKDIR 已包含 services/, 此操作为无操作
# ═══════════════════════════════════════════════════════════════
_SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

from .langchain_workflow import build_workflow
from .workflow_state import ArchitectureWorkflowState

# ═══════════════════════════════════════════════════════════════
# 缓存后端选择 — 环境变量 CACHE_BACKEND 控制
#   memory: 基于 dict + TTL 的线程安全内存缓存 (默认)
#   sqlite: 基于 SQLite 的持久化缓存 (跨重启保留)
# 两种后端提供相同的 get/set/clear/stats 接口
# ═══════════════════════════════════════════════════════════════
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory").strip().lower()
if CACHE_BACKEND == "sqlite":
    from common.cache.sqlite_cache import get as cache_get, set as cache_set, clear as cache_clear, stats as cache_stats
else:
    from common.cache.simple_cache import get as cache_get, set as cache_set, clear as cache_clear, stats as cache_stats

from common.cache.hash_utils import cache_key, knowledge_version

# ── 日志配置 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api-gateway")

# ═══════════════════════════════════════════════════════════════
# FastAPI 应用初始化 + CORS
# 前端 (localhost:3000) 可跨域访问本服务 (localhost:8000)
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="API Gateway", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# 下游微服务地址 — 环境变量注入 (Docker Compose 中自动设置)
# 本地开发默认 localhost, Docker 中是容器名 (requirements-agent:8001 等)
# ═══════════════════════════════════════════════════════════════
REQUIREMENTS_AGENT_URL = os.getenv("REQUIREMENTS_AGENT_URL", "http://localhost:8001")
MATCHING_AGENT_URL = os.getenv("MATCHING_AGENT_URL", "http://localhost:8002")
EVALUATION_AGENT_URL = os.getenv("EVALUATION_AGENT_URL", "http://localhost:8003")
REFACTORING_AGENT_URL = os.getenv("REFACTORING_AGENT_URL", "http://localhost:8005")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

# ═══════════════════════════════════════════════════════════════
# LangGraph 工作流 — 模块加载时编译一次
# ═══════════════════════════════════════════════════════════════
_langgraph_app = build_workflow(
    req_url=REQUIREMENTS_AGENT_URL,
    match_url=MATCHING_AGENT_URL,
    eval_url=EVALUATION_AGENT_URL,
)
logger.info(f"API Gateway workflow engine: langgraph")
logger.info(f"Cache backend: {CACHE_BACKEND}, kv={knowledge_version()}")


# ═══════════════════════════════════════════════════════════════
# Pydantic 模型 — 请求/响应校验
# ═══════════════════════════════════════════════════════════════

class RecommendRequest(BaseModel):
    """推荐请求体 — min_length=5 确保至少是一句有意义的需求描述."""
    requirement: str = Field(..., min_length=5, description="Natural language requirement text")


class RecommendResponse(BaseModel):
    """推荐响应体 — 从原始编排结果封装, 所有字段向后兼容."""
    extracted_features: Dict[str, Any]
    feature_hits: Dict[str, Any]
    candidates: list[Dict[str, Any]]
    final_report: Dict[str, Any]
    workflow_engine: str = "manual"
    workflow_trace: List[Dict[str, Any]] = []
    cache_hit: bool = False


# ═══════════════════════════════════════════════════════════════
# 健康检查端点
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
def health() -> Dict[str, str]:
    """返回网关状态: 编排引擎类型 + 缓存后端."""
    return {
        "status": "ok",
        "service": "api-gateway",
        "workflow_engine": "langgraph",
        "cache_backend": CACHE_BACKEND,
    }

async def _langgraph_orchestrate(payload: RecommendRequest) -> Dict[str, Any]:
    """LangGraph StateGraph 编排 — 主路径.

    【工作原理】
    1. 构造初始状态 (只有 requirement, 其他字段为空)
    2. 将状态传给编译后的 StateGraph.ainvoke()
    3. LangGraph 按预定义 DAG 串行执行四个节点
    4. 从最终状态中提取结果字段

    
    - 状态管理: TypedDict 自动传递, 不需要手动拼请求/响应
    - 容错: 每个节点独立 try/except + trace 记录
    - 可观测: trace 包含 4 个节点的记录 vs 手动路径的 3 个节点
    """
    initial_state: ArchitectureWorkflowState = {
        "requirement": payload.requirement,
        "extracted_features": {},
        "feature_hits": {},
        "candidates": [],
        "combination_candidates": [],
        "final_report": {},
        "errors": [],
        "trace": [],
    }
    result = await _langgraph_app.ainvoke(initial_state)
    return {
        "extracted_features": result.get("extracted_features", {}),
        "feature_hits": result.get("feature_hits", {}),
        "llm_disputed": result.get("llm_disputed", {}),
        "arch_inclination": result.get("arch_inclination", {}),
        "candidates": result.get("candidates", []),
        "final_report": result.get("final_report", {}),
        "workflow_engine": "langgraph",
        "workflow_trace": result.get("trace", []),
    }


# ═══════════════════════════════════════════════════════════════
# 主推荐端点 — 系统的唯一对外接口
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/recommend")
async def recommend(payload: RecommendRequest) -> Dict[str, Any]:
    """从自然语言需求到架构推荐报告的完整入口.

    【执行流程】分三个阶段, 每阶段独立容错:

    阶段1 — 请求级缓存:
      计算 SHA-256 缓存键 (需求文本 + LLM 模型名)
      命中 → 直接返回, 耗时 < 5ms

    阶段2 — LangGraph 编排:
      StateGraph extract → match → evaluate → trace → END

    阶段3 — 重构建议 (非阻塞):
      装饰性调用 refactoring-agent
      失败不抛异常, 返回空 advince

    阶段4 — 写入缓存:
      结果存入内存/SQLite 缓存 (TTL 1h)
    """
    t_total_start = time.perf_counter()
    logger.info(f"Received recommendation request: {payload.requirement[:50]}...")

    # 阶段1: 请求级缓存
    # cache_key() = SHA-256(需求文本 + LLM模型名) 的前 16 位
    # 知识库版本变化时 knowledge_version 也会变 → 旧缓存自动失效
    key = cache_key(payload.requirement, LLM_MODEL)
    cached = cache_get(key)
    if cached is not None:
        t_total = round((time.perf_counter() - t_total_start) * 1000)
        logger.info(f"Cache HIT for key={key} (total {t_total}ms)")
        cached["cache_hit"] = True
        return cached

    # 阶段2: LangGraph 编排执行
    result = await _langgraph_orchestrate(payload)

    result["cache_hit"] = False

    # 阶段3: 重构建议 — 非阻塞装饰性调用
    # 独立 HTTP 连接 (不重用编排阶段的 httpx 客户端)
    # 8s 超时控制 + try/except 确保不阻塞主链路
    refactoring_advice = {}
    try:
        async with httpx.AsyncClient(timeout=25.0, trust_env=False) as ref_client:
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

    # 阶段4: 写入缓存
    cache_set(key, result)

    t_total = round((time.perf_counter() - t_total_start) * 1000)
    logger.info(
        f"Recommendation successful: {result['final_report'].get('recommended_style')} "
        f"(engine={result['workflow_engine']}, cache=miss, total {t_total}ms)"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 缓存管理端点 — 可观测 + 手动清空
# ═══════════════════════════════════════════════════════════════

@app.get("/cache/stats")
def get_cache_stats() -> Dict[str, Any]:
    """缓存统计: hits / misses / hit_rate / entries / ttl / knowledge_version."""
    stats = cache_stats()
    stats["knowledge_version"] = knowledge_version()
    return stats


@app.api_route("/cache/clear", methods=["GET", "POST"])
def clear_cache() -> Dict[str, Any]:
    """清空所有缓存条目 (支持 GET + POST, 方便浏览器/curl 直接调用)."""
    count = cache_clear()
    return {"status": "ok", "cleared": count}
