"""Evaluation Subgraph — 4 子节点 + Send() 并行扇出.

将 evaluate() 的 asyncio.gather 替换为 LangGraph Send() 声明式并行:
  llm_vote_style() 和 llm_summary() 注册为独立并行节点,
  LangGraph 引擎同时调度两者, 结果在 merge 节点汇聚.

【子图拓扑】
  START → sort → Send(vote) + Send(summary) → merge → END
                     └── 并行扇出 ──┘

【Send() 的价值】
  原来用 asyncio.gather 是 Python 协程级并发 — 图结构不知道两个调用是并行的.
  Send() 把并行关系声明在图结构中 — 可视化、可追踪、可在 trace 中看到两条并行分支.
"""

import json
import logging
import time
from typing import Any, Dict, List, TypedDict

import httpx

logger = logging.getLogger("evaluation-agent.subgraph")

import os as _os

# 环境变量 — 模块级初始化 + build_evaluation_subgraph() 可覆写
LLM_API_BASE = _os.getenv("LLM_API_BASE", "").strip()
LLM_API_KEY = _os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = _os.getenv("LLM_MODEL", "").strip()
KNOWLEDGE_BASE_URL = _os.getenv("KNOWLEDGE_BASE_URL", "http://localhost:8004").strip()


def _configure(llm_base: str, llm_key: str, llm_model: str, kb_url: str) -> None:
    global LLM_API_BASE, LLM_API_KEY, LLM_MODEL, KNOWLEDGE_BASE_URL
    LLM_API_BASE = llm_base
    LLM_API_KEY = llm_key
    LLM_MODEL = llm_model
    KNOWLEDGE_BASE_URL = kb_url


# ═══════════════════════════════════════════════════════════════
# 纯函数 — 从 main.py 提取, Subgraph 和 do_plan 共用
# ═══════════════════════════════════════════════════════════════

REASON_LABELS_ZH = {
    "high_concurrency": "高并发场景处理能力强", "real_time": "实时性需求匹配度高",
    "reliability": "可靠性保障机制完善", "scalability": "可扩展性强，便于后续扩展",
    "complex_business": "适合复杂业务逻辑", "strict_consistency": "满足强一致性要求",
    "deployment_constraint": "契合部署约束条件", "data_intensive": "适合数据密集型处理",
    "team_size_large": "支持多团队协作开发", "security": "安全性保障完备",
    "llm_vote_bonus": "大模型辅助判断确认",
}

STYLE_RISK_MAP: Dict[str, Dict[str, List[str]]] = {
    "Event-Driven Architecture": {
        "main_risks": ["事件溯源实现复杂度高，调试困难",
                       "事件一致性设计难度大，需额外处理幂等与乱序",
                       "分布式链路追踪和监控成本较高"],
        "suggestions": ["引入消息队列（如Kafka/RabbitMQ）并设置死信队列",
                        "建立事件Schema版本管理，保证向前兼容",
                        "部署分布式追踪系统（如Jaeger/Zipkin）"],
    },
    "Microservices": {
        "main_risks": ["分布式系统复杂度高，事务一致性难保障",
                       "服务间通信延迟和网络故障风险增大",
                       "运维成本高，需完善CI/CD和容器编排"],
        "suggestions": ["采用Saga模式处理分布式事务",
                        "引入服务网格（如Istio）管理服务间通信",
                        "建立统一的API网关和认证授权中心"],
    },
    "Layered Architecture": {
        "main_risks": ["跨层调用带来性能开销，高并发场景可能成为瓶颈",
                       "层级耦合可能导致变更影响面大",
                       "横向扩展能力有限，不适合极端流量场景"],
        "suggestions": ["严格遵循单向依赖，避免跨层直接调用",
                        "核心业务层可结合CQRS读写分离缓解性能压力",
                        "通过水平扩展+负载均衡提升吞吐量"],
    },
}


def _localize_reasons(reasons: List[str]) -> List[str]:
    zh: List[str] = []
    for r in reasons:
        for eng_key, zh_label in REASON_LABELS_ZH.items():
            if eng_key in r:
                zh.append(zh_label)
                break
        else:
            zh.append(r)
    return list(dict.fromkeys(zh))


def _dynamic_risks(style_name: str, candidates: List[Dict[str, Any]] | None = None) -> Dict[str, List[str]]:
    if style_name in STYLE_RISK_MAP:
        return STYLE_RISK_MAP[style_name]
    return {
        "main_risks": ["架构复杂度与需求规模不匹配的风险",
                       "开发和运维团队对选定架构的熟悉程度",
                       "后续演进中架构腐化的可能性"],
        "suggestions": ["持续记录架构决策（ADR）并定期评审",
                        "建立技术债务看板，规划重构窗口",
                        "引入架构适配度度量指标并自动化检查"],
    }


# ═══════════════════════════════════════════════════════════════
# LLM 调用 — 异步函数, 被子节点调用
# ═══════════════════════════════════════════════════════════════

async def llm_vote_style(requirement: str, candidates: List[Dict[str, Any]]) -> str | None:
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL) or not candidates:
        return None
    style_names = [c.get("style", "") for c in candidates if c.get("style")]
    if not style_names:
        return None

    logger.info(f"[subgraph] LLM vote among {style_names}")
    prompt = (
        "Select one best architecture style from given candidates. "
        "Return only the exact style name, no extra words.\n"
        f"Requirement: {requirement}\nCandidates: {style_names}\n"
    )
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {"model": LLM_MODEL, "messages": [
        {"role": "system", "content": "You are a strict architecture judge."},
        {"role": "user", "content": prompt},
    ], "temperature": 0.0}

    try:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            if text in style_names:
                return text
            logger.warning(f"[subgraph] LLM voted unknown: {text}")
    except Exception as e:
        logger.error(f"[subgraph] LLM vote failed: {e}")
    return None


async def llm_summary(requirement: str, candidates: List[Dict[str, Any]], best_style: str) -> str:
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL):
        return _fallback_summary(best_style, candidates)

    alt_names = [c.get("style", "") for c in candidates if c.get("style") != best_style]
    alt_styles = ", ".join(alt_names[:2]) if alt_names else "none"
    candidates_json = json.dumps(candidates, ensure_ascii=False)

    try:
        from common.prompts.evaluation_few_shot import build_few_shot_prompt
        prompt = build_few_shot_prompt(requirement, best_style, alt_styles, candidates_json)
    except ImportError:
        prompt = (
            "You are a senior software architecture reviewer. Output in Chinese.\n\n"
            "1. Recommended architecture: [primary] and [alternate]\n"
            "2. Reasons (2-3 points)\n"
            "3. Pros and cons\n"
            "4. Risks and suggestions\n\n"
            f"Requirement: {requirement}\nPrimary: {best_style}\nAlternate: {alt_styles}\n"
            f"Candidates: {candidates_json}\n"
        )

    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {"model": LLM_MODEL, "messages": [
        {"role": "system", "content": "You are a senior software architecture reviewer. Output in Chinese."},
        {"role": "user", "content": prompt},
    ], "temperature": 0.3}

    try:
        async with httpx.AsyncClient(timeout=25.0, trust_env=False) as client:
            resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[subgraph] LLM summary failed: {e}")
        return _fallback_summary(best_style, candidates)


def _fallback_summary(best_style: str, candidates: List[Dict[str, Any]]) -> str:
    alt = [c.get("style") for c in candidates if c.get("style") != best_style][:2]
    best_pros = next((c.get("pros", []) for c in candidates if c.get("style") == best_style), [])
    best_cons = next((c.get("cons", []) for c in candidates if c.get("style") == best_style), [])
    lines = [f"1. 推荐架构：{best_style}（核心推荐）"]
    if alt:
        lines.append(f"   备选架构：{'、'.join(alt)}")
    lines.append("")
    lines.append("2. 推荐理由：")
    reasons = next((c.get("reasons", []) for c in candidates if c.get("style") == best_style), [])
    for r in _localize_reasons(reasons)[:3]:
        lines.append(f"   - {r}")
    lines.append("")
    lines.append("3. 优缺点分析：")
    if best_pros:
        lines.append(f"   √ 优点：{'、'.join(best_pros)}")
    if best_cons:
        lines.append(f"   × 缺点：{'、'.join(best_cons)}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 四个子节点
# ═══════════════════════════════════════════════════════════════

async def _sort_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 1: 按规则分排序 candidates."""
    candidates = state.get("candidates", [])
    ranked = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
    rule_best = ranked[0] if ranked else {}
    return {"ranked": ranked, "rule_best_style": rule_best.get("style", "")}


async def _vote_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 2a: LLM 投票 (Send 并行分支)."""
    t0 = time.perf_counter()
    requirement = state.get("requirement", "")
    ranked = state.get("ranked", [])
    vote = await llm_vote_style(requirement, ranked)
    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] vote_node: {vote}, {elapsed}ms")
    return {"llm_vote": vote, "_trace_vote": elapsed}


async def _summary_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 2b: LLM 摘要 (Send 并行分支)."""
    t0 = time.perf_counter()
    requirement = state.get("requirement", "")
    ranked = state.get("ranked", [])
    rule_best_style = state.get("rule_best_style", "")
    note = await llm_summary(requirement, ranked, rule_best_style)
    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] summary_node done, {elapsed}ms")
    return {"llm_note": note, "_trace_summary": elapsed}


async def _merge_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """子节点 3: 汇聚投票+摘要, 构建最终报告."""
    t0 = time.perf_counter()
    ranked = state.get("ranked", [])
    llm_vote = state.get("llm_vote")
    llm_note = state.get("llm_note", "")
    requirement = state.get("requirement", "")
    features = state.get("features", {})
    combos = state.get("combination_candidates", [])

    # 投票加分
    if llm_vote:
        for item in ranked:
            if item.get("style") == llm_vote:
                item["score"] = item.get("score", 0) + 1
                item.setdefault("reasons", []).append("LLM投票加分")

    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    best = ranked[0] if ranked else {}
    best_style = best.get("style", "")
    best_zh = best.get("style_zh", best_style)

    # 对比矩阵
    comparison_matrix = []
    for i, item in enumerate(ranked):
        comparison_matrix.append({
            "style": item["style"], "style_zh": item.get("style_zh", item["style"]),
            "score": item["score"],
            "recommendation_type": "核心推荐" if i == 0 else "备选架构",
            "pros": item.get("pros", []), "pros_zh": item.get("pros_zh", []),
            "cons": item.get("cons", []), "cons_zh": item.get("cons_zh", []),
            "key_reasons": _localize_reasons(item.get("reasons", [])),
            "key_reasons_raw": item.get("reasons", []),
            "topology_mermaid": item.get("topology_mermaid", ""),
        })

    risk_info = _dynamic_risks(best_style)

    # 组合推荐
    recommended_combination = {}
    if combos:
        bc = combos[0]
        recommended_combination = {
            "name": bc.get("combination_name", ""),
            "name_zh": bc.get("combination_name_zh", ""),
            "combo_score": bc.get("combo_score", 0),
            "components": bc.get("component_details", []),
            "synergy_zh": bc.get("synergy_zh", ""),
            "reasons": bc.get("reasons", []),
            "complexity_penalty": bc.get("complexity_penalty", 0),
            "topology_mermaid": bc.get("topology_mermaid", ""),
        }

    report = {
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
        "risk_and_suggestions": risk_info,
        "recommended_combination": recommended_combination,
        "combination_candidates": combos[:3],
    }

    # ADR 写入 (非阻塞)
    adr_status = "not_generated"
    adr_id = None
    try:
        graph_evidence = {
            "matched_attributes": best.get("matched_attributes", []),
            "matched_scenarios": best.get("matched_scenarios", []),
            "combinable_styles": best.get("combinable_styles", []),
            "graph_score": best.get("graph_score", 0),
        }
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            adr_resp = await client.post(f"{KNOWLEDGE_BASE_URL}/adr", json={
                "requirement": requirement, "extracted_features": features,
                "candidates": [c for c in ranked[:3]],
                "recommended_style": best_style, "recommended_style_zh": best_zh,
                "alternative_styles": [c.get("style") for c in ranked[1:]],
                "decision_basis": report["decision_basis"],
                "risk_and_suggestions": risk_info, "graph_evidence": graph_evidence,
            })
            if adr_resp.status_code == 200:
                adr_id = adr_resp.json().get("adr_id")
                adr_status = "ok"
    except Exception as e:
        logger.warning(f"[subgraph] ADR failed (non-fatal): {e}")
        adr_status = "failed"

    report["adr"] = {
        "adr_id": adr_id, "adr_status": adr_status,
        "adr_summary": f"ADR for '{requirement[:40]}...' → {best_style}" if adr_id else None,
        "api_path": f"/adr/{adr_id}" if adr_id else None,
    }

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(f"[subgraph] merge_node done: {best_style}, {elapsed}ms")
    return {"final_report": report, "_trace_merge": elapsed}


# ═══════════════════════════════════════════════════════════════
# 子图工厂 — Send() 并行扇出
# ═══════════════════════════════════════════════════════════════

class EvalSubgraphState(TypedDict, total=False):
    """TypedDict 定义各字段独立 channel — Send() 并行分支可同时写入不同字段."""
    requirement: str
    features: Dict[str, bool]
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]]
    ranked: List[Dict[str, Any]]
    rule_best_style: str
    llm_vote: Any
    llm_note: str
    final_report: Dict[str, Any]
    _trace_vote: int
    _trace_summary: int
    _trace_merge: int


def build_evaluation_subgraph(llm_base: str = "", llm_key: str = "",
                               llm_model: str = "", kb_url: str = "http://localhost:8004"):
    """编译 evaluation 子图: sort → Send(vote ∥ summary) → merge.

    Send() 声明两个节点并行执行 — LangGraph 自动管理并发调度,
    替代原来的 asyncio.gather 手动并行.
    """
    try:
        from langgraph.graph import StateGraph, END, START
        from langgraph.types import Send
    except ImportError:
        logger.warning("langgraph not installed, evaluation subgraph unavailable")
        return None

    _configure(llm_base, llm_key, llm_model, kb_url)

    try:
        subgraph = StateGraph(EvalSubgraphState)

        subgraph.add_node("sort", _sort_node)
        subgraph.add_node("vote", _vote_node)
        subgraph.add_node("summary", _summary_node)
        subgraph.add_node("merge", _merge_node)

        subgraph.add_edge(START, "sort")

        # Send() 并行扇出 — 两个 LLM 调用被 LangGraph 同时调度
        def fan_out_vote_summary(state: Dict[str, Any]):
            return [Send("vote", state), Send("summary", state)]

        subgraph.add_conditional_edges("sort", fan_out_vote_summary,
                                        path_map={"vote": "vote", "summary": "summary"})

        subgraph.add_edge("vote", "merge")
        subgraph.add_edge("summary", "merge")
        subgraph.add_edge("merge", END)

        compiled = subgraph.compile()
        logger.info("Evaluation subgraph compiled (sort → Send(vote∥summary) → merge)")
        return compiled
    except Exception as e:
        logger.error(f"Failed to build evaluation subgraph: {e}")
        return None
