import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

# Auto-load .env if exists (fallback for when not launched via docker-compose)
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluation-agent")

app = FastAPI(title="Evaluation Agent", version="0.1.0")

LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()


class EvaluateRequest(BaseModel):
    requirement: str
    features: Dict[str, bool]
    candidates: List[Dict[str, Any]]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "evaluation-agent"}


async def llm_summary(requirement: str, candidates: List[Dict[str, Any]], best_style: str) -> str:
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL):
        logger.warning("LLM not configured, using fallback summary.")
        return _fallback_summary(best_style, candidates)

    cand_names = [c.get("style", "") for c in candidates if c.get("style") != best_style]
    logger.info(f"Requesting LLM summary for {len(candidates)} candidates...")
    prompt = (
        "你是一个软件架构评审专家。根据用户需求和候选架构，请用中文输出以下内容：\n\n"
        "1. 推荐架构：【核心推荐】和【备选架构】\n"
        "2. 推荐理由：（2-3条要点）\n"
        "3. 优缺点分析：\n"
        "   √ 优点：...\n"
        "   × 缺点：...\n\n"
        f"用户需求：{requirement}\n"
        f"核心推荐：{best_style}\n"
        f"备选架构：{', '.join(cand_names[:2]) if cand_names else '无'}\n"
        f"候选详情：{json.dumps(candidates, ensure_ascii=False)}\n"
    )

    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a senior software architecture reviewer. Output in Chinese with clear structure."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=25.0, trust_env=False) as client:
            resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            logger.info("LLM summary generated successfully.")
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return _fallback_summary(best_style, candidates)


def _fallback_summary(best_style: str, candidates: List[Dict[str, Any]]) -> str:
    """规则引擎降级摘要，按参考案例格式输出."""
    import json as _json
    alt = [c.get("style") for c in candidates if c.get("style") != best_style][:2]
    best_pros = next((c.get("pros", []) for c in candidates if c.get("style") == best_style), [])
    best_cons = next((c.get("cons", []) for c in candidates if c.get("style") == best_style), [])

    lines = [
        f"1. 推荐架构：{best_style}（核心推荐）",
    ]
    if alt:
        lines.append(f"   备选架构：{'、'.join(alt)}")
    lines.append("")
    lines.append("2. 推荐理由：")
    reasons = next((c.get("reasons", []) for c in candidates if c.get("style") == best_style), [])
    zh_reasons = _localize_reasons(reasons)
    for r in zh_reasons[:3]:
        lines.append(f"   - {r}")
    lines.append("")
    lines.append("3. 优缺点分析：")
    if best_pros:
        lines.append(f"   √ 优点：{'、'.join(best_pros)}")
    if best_cons:
        lines.append(f"   × 缺点：{'、'.join(best_cons)}")
    return "\n".join(lines)


async def llm_vote_style(requirement: str, candidates: List[Dict[str, Any]]) -> str | None:
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL) or not candidates:
        return None

    style_names = [item.get("style", "") for item in candidates if item.get("style")]
    if not style_names:
        return None

    logger.info(f"Requesting LLM vote among {style_names}...")
    prompt = (
        "Select one best architecture style from given candidates. "
        "Return only the exact style name, no extra words.\n"
        f"Requirement: {requirement}\n"
        f"Candidates: {style_names}\n"
    )

    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict architecture judge."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            if text in style_names:
                logger.info(f"LLM voted for: {text}")
                return text
            logger.warning(f"LLM voted for unknown style: {text}")
    except Exception as e:
        logger.error(f"LLM vote request failed: {e}")
        return None

    return None


REASON_LABELS_ZH = {
    "high_concurrency": "高并发场景处理能力强",
    "real_time": "实时性需求匹配度高",
    "reliability": "可靠性保障机制完善",
    "scalability": "可扩展性强，便于后续扩展",
    "complex_business": "适合复杂业务逻辑",
    "strict_consistency": "满足强一致性要求",
    "deployment_constraint": "契合部署约束条件",
    "data_intensive": "适合数据密集型处理",
    "team_size_large": "支持多团队协作开发",
    "security": "安全性保障完备",
    "llm_vote_bonus": "大模型辅助判断确认",
}


def _localize_reasons(reasons: List[str]) -> List[str]:
    """将规则理由转为中文可读表述."""
    zh: List[str] = []
    for r in reasons:
        for eng_key, zh_label in REASON_LABELS_ZH.items():
            if eng_key in r:
                zh.append(zh_label)
                break
        else:
            zh.append(r)
    return list(dict.fromkeys(zh))


STYLE_RISK_MAP: Dict[str, Dict[str, List[str]]] = {
    "Event-Driven Architecture": {
        "main_risks": [
            "事件溯源实现复杂度高，调试困难",
            "事件一致性设计难度大，需额外处理幂等与乱序",
            "分布式链路追踪和监控成本较高",
        ],
        "suggestions": [
            "引入消息队列（如Kafka/RabbitMQ）并设置死信队列",
            "建立事件Schema版本管理，保证向前兼容",
            "部署分布式追踪系统（如Jaeger/Zipkin）",
        ],
    },
    "Microservices": {
        "main_risks": [
            "分布式系统复杂度高，事务一致性难保障",
            "服务间通信延迟和网络故障风险增大",
            "运维成本高，需完善CI/CD和容器编排",
        ],
        "suggestions": [
            "采用Saga模式处理分布式事务",
            "引入服务网格（如Istio）管理服务间通信",
            "建立统一的API网关和认证授权中心",
        ],
    },
    "Layered Architecture": {
        "main_risks": [
            "跨层调用带来性能开销，高并发场景可能成为瓶颈",
            "层级耦合可能导致变更影响面大",
            "横向扩展能力有限，不适合极端流量场景",
        ],
        "suggestions": [
            "严格遵循单向依赖，避免跨层直接调用",
            "核心业务层可结合CQRS读写分离缓解性能压力",
            "通过水平扩展+负载均衡提升吞吐量",
        ],
    },
}


def _dynamic_risks(style_name: str, candidates: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """根据推荐风格生成针对性风险和缓解建议."""
    if style_name in STYLE_RISK_MAP:
        return STYLE_RISK_MAP[style_name]
    # 通用回退
    return {
        "main_risks": [
            "架构复杂度与需求规模不匹配的风险",
            "开发和运维团队对选定架构的熟悉程度",
            "后续演进中架构腐化的可能性",
        ],
        "suggestions": [
            "持续记录架构决策（ADR）并定期评审",
            "建立技术债务看板，规划重构窗口",
            "引入架构适配度度量指标并自动化检查",
        ],
    }


@app.post("/evaluate")
async def evaluate(payload: EvaluateRequest) -> Dict[str, Any]:
    ranked = sorted(payload.candidates, key=lambda x: x.get("score", 0), reverse=True)

    # Pre-compute rule-based best so LLM summary can run concurrently with LLM vote
    rule_best = ranked[0] if ranked else {}
    rule_best_style = rule_best.get("style", "")

    # Run two independent LLM calls in parallel (vote + summary don't depend on each other)
    llm_vote, llm_note = await asyncio.gather(
        llm_vote_style(payload.requirement, ranked),
        llm_summary(payload.requirement, ranked, rule_best_style),
    )

    # Hybrid reasoning: rule score is primary, LLM vote adds a lightweight tie-break bonus.
    if llm_vote:
        for item in ranked:
            if item.get("style") == llm_vote:
                item["score"] = item.get("score", 0) + 1
                item.setdefault("reasons", []).append("llm_vote_bonus")

    ranked = sorted(ranked, key=lambda x: x.get("score", 0), reverse=True)
    best = ranked[0] if ranked else {}
    best_style = best.get("style", "")

    comparison_matrix = []
    for i, item in enumerate(ranked):
        zh_reasons = _localize_reasons(item.get("reasons", []))
        comparison_matrix.append({
            "style": item["style"],
            "style_zh": item.get("style_zh", item["style"]),
            "score": item["score"],
            "recommendation_type": "核心推荐" if i == 0 else "备选架构",
            "pros": item.get("pros", []),
            "pros_zh": item.get("pros_zh", []),
            "cons": item.get("cons", []),
            "cons_zh": item.get("cons_zh", []),
            "key_reasons": zh_reasons,
            "key_reasons_raw": item.get("reasons", []),
            "topology_mermaid": item.get("topology_mermaid", ""),
        })

    best_zh = best.get("style_zh", best_style)
    return {
        "recommended_style": best_style,
        "recommended_style_zh": best_zh,
        "alternative_styles": [c.get("style") for c in ranked[1:]],
        "alternative_styles_zh": [c.get("style_zh", c.get("style", "")) for c in ranked[1:]],
        "decision_basis": {
            "rule_engine": _localize_reasons(best.get("reasons", [])),
            "rule_engine_raw": best.get("reasons", []),
            "llm_summary": llm_note,
            "llm_vote": llm_vote,
        },
        "comparison_matrix": comparison_matrix,
        "risk_and_suggestions": _dynamic_risks(best_style, ranked),
    }
