"""架构重构建议微服务 — 检测架构坏味并生成渐进式迁移方案.

规则引擎主导 (关键词检测 + 特征推断), LLM 可选润色.
LLM 不可用时使用结构化规则模板.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

# ── 本地开发: services/ → sys.path ──
_SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("refactoring-agent")

app = FastAPI(title="Refactoring Agent", version="0.1.0")

LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()


class RefactorRequest(BaseModel):
    requirement: str
    current_architecture: Optional[str] = None
    features: Dict[str, bool] = {}
    candidates: List[Dict[str, Any]] = []
    recommended_style: str = ""
    recommended_combination: Dict[str, Any] = {}


# ── 重构关键词词典 ────────────────────────────────────────────

REFACTORING_KEYWORDS = [
    "已有系统", "老系统", "旧系统", "遗留系统",
    "单体", "单体系统", "单体架构",
    "耦合严重", "高度耦合", "紧耦合",
    "重构", "迁移", "拆分", "解耦",
    "性能瓶颈", "扩展困难", "维护困难",
    "团队膨胀", "发布周期长",
]

# ── 架构坏味检测 ──────────────────────────────────────────────

ARCHITECTURE_SMELLS: Dict[str, Dict[str, Any]] = {
    "monolith_coupling": {
        "name_zh": "单体耦合过重",
        "keywords": ["单体", "耦合严重", "紧耦合", "高度耦合"],
        "description": "业务逻辑高度耦合在单一进程中，变更影响面大，部署周期长。",
    },
    "scaling_bottleneck": {
        "name_zh": "扩展瓶颈",
        "keywords": ["性能瓶颈", "扩展困难", "高并发"],
        "description": "当前架构无法水平扩展，高并发场景下性能下降明显。",
    },
    "slow_release": {
        "name_zh": "发布周期过长",
        "keywords": ["发布周期长", "团队膨胀"],
        "description": "多团队共用一个代码库和部署管道，发布互相阻塞。",
    },
    "legacy_lockin": {
        "name_zh": "遗留系统锁定",
        "keywords": ["遗留系统", "老系统", "旧系统", "已有系统"],
        "description": "遗留技术栈限制现代化改造，需渐进式替换。",
    },
    "data_coupling": {
        "name_zh": "数据层耦合",
        "keywords": ["共享数据库", "数据耦合", "库存耦合"],
        "description": "多个业务模块共享数据库，读写冲突和数据一致性问题突出。",
    },
}

# ── 重构模式模板 ──────────────────────────────────────────────

REFACTORING_PATTERNS = {
    "strangler_fig": {
        "name": "Strangler Fig Pattern",
        "name_zh": "绞杀者模式",
        "when": "需要从单体逐步迁移到微服务，不能一次性重写。",
        "steps": [
            "1. 识别并隔离目标业务边界（如订单模块），建立 API 网关路由规则。",
            "2. 新建独立微服务，逐步将目标功能从单体中迁移出来。",
            "3. 通过网关将对应路由指向新服务，单体中该功能逐步退役。",
            "4. 重复以上步骤，逐模块替换，直至单体完全退役。",
        ],
    },
    "anti_corruption_layer": {
        "name": "Anti-Corruption Layer",
        "name_zh": "防腐层模式",
        "when": "新系统需要与遗留系统交互，但不能让遗留模型污染新系统领域模型。",
        "steps": [
            "1. 定义新系统的领域模型和接口契约。",
            "2. 在边界处建立防腐层（Adapter），负责遗留模型 ↔ 新模型的双向转换。",
            "3. 所有跨系统调用必须经过防腐层，禁止直接访问遗留数据库。",
            "4. 遗留系统逐步退役时，只需移除对应 Adapter，不影响新系统核心。",
        ],
    },
    "modular_monolith_first": {
        "name": "Modular Monolith First",
        "name_zh": "模块化单体优先",
        "when": "团队规模中等，尚未准备好全面微服务化，但需要改善代码组织。",
        "steps": [
            "1. 在单体内部按业务边界拆分为独立模块（package/namespace）。",
            "2. 模块间通过明确的接口通信，禁止跨模块直接访问数据库表。",
            "3. 建立模块级别的测试和构建边界。",
            "4. 当某模块需要独立部署/扩容时，再将其抽取为独立服务。",
        ],
    },
    "cqrs_refactor": {
        "name": "CQRS Read/Write Split",
        "name_zh": "CQRS 读写分离重构",
        "when": "读写负载严重不均衡，查询性能瓶颈影响核心写操作。",
        "steps": [
            "1. 梳理系统的读写操作比例和热点查询。",
            "2. 将写模型和读模型在代码层面分离，使用不同的数据访问对象。",
            "3. 引入事件机制（如 CDC 或应用事件）同步写数据库到读数据库。",
            "4. 读模型可使用更适合查询的存储（如 Elasticsearch、只读副本）。",
        ],
    },
    "event_driven_migration": {
        "name": "Event-Driven Migration",
        "name_zh": "事件驱动迁移",
        "when": "需要解耦紧耦合的服务间同步调用，引入异步通信。",
        "steps": [
            "1. 梳理当前服务间的同步调用链，识别可异步化的调用。",
            "2. 引入消息队列（Kafka/RabbitMQ），在生产者端发布领域事件。",
            "3. 消费者订阅事件，异步执行后续处理逻辑。",
            "4. 保留同步调用作为 fallback，通过 feature flag 逐步切换。",
        ],
    },
}

# ── 规则检测 ──────────────────────────────────────────────────

def detect_smells(requirement: str, features: Dict[str, bool]) -> List[Dict[str, Any]]:
    """基于关键词和特征维度检测架构坏味."""
    detected: List[Dict[str, Any]] = []
    text_lower = requirement.lower()

    for key, smell in ARCHITECTURE_SMELLS.items():
        if any(kw in requirement for kw in smell["keywords"]):
            detected.append({"id": key, "name_zh": smell["name_zh"], "description": smell["description"]})

    return detected


def select_patterns(req: str, features: Dict[str, bool],
                    recommended_style: str) -> List[Dict[str, Any]]:
    """根据需求和推荐风格选择适用的重构模式."""
    selected: List[Dict[str, Any]] = []

    # 单体拆分 → Strangler Fig
    if any(kw in req for kw in ["单体", "拆分", "耦合严重", "已有系统", "老系统", "重构"]):
        selected.append(REFACTORING_PATTERNS["strangler_fig"])

    # 遗留系统 → Anti-Corruption Layer
    if any(kw in req for kw in ["遗留系统", "老系统", "旧系统", "已有系统"]):
        if not any(p["name"] == "Anti-Corruption Layer" for p in selected):
            selected.append(REFACTORING_PATTERNS["anti_corruption_layer"])

    # 模块化优先 (不极端微服务)
    if features.get("complex_business") and not features.get("team_size_large"):
        selected.append(REFACTORING_PATTERNS["modular_monolith_first"])

    # CQRS for read/write imbalance
    if features.get("data_intensive") and features.get("high_concurrency"):
        if "CQRS" in recommended_style:
            selected.append(REFACTORING_PATTERNS["cqrs_refactor"])

    # Event-Driven migration
    if "Event-Driven" in recommended_style and features.get("real_time"):
        selected.append(REFACTORING_PATTERNS["event_driven_migration"])

    return selected


def build_rule_template(req: str, smells: List[Dict[str, Any]],
                        patterns: List[Dict[str, Any]],
                        recommended_style: str,
                        recommended_combo: Dict[str, Any],
                        features: Dict[str, bool] | None = None) -> Dict[str, Any]:
    """生成基于规则的完整重构建议模板."""
    refactoring_needed = len(smells) > 0 or any(
        kw in req for kw in ["重构", "迁移", "拆分", "单体", "耦合", "老系统"]
    )

    target = recommended_combo.get("name") or recommended_style or "待定"
    target_zh = recommended_combo.get("name_zh") or recommended_style

    migration_steps: List[str] = []
    if patterns:
        for p in patterns[:2]:  # 最多 2 个模式
            migration_steps.append(f"【{p.get('name_zh', p['name'])}】")
            migration_steps.extend(p.get("steps", []))

    if not migration_steps:
        migration_steps = [
            "1. 评估当前架构的技术债务和瓶颈点，建立重构优先级矩阵。",
            "2. 对高优先级模块进行代码结构梳理，提取领域边界。",
            "3. 引入自动化测试覆盖核心业务逻辑，确保重构的安全性。",
            "4. 通过 feature flag 和灰度发布逐步上线重构变更。",
        ]

    risks: List[str] = []
    if "Microservices" in recommended_style:
        risks.append("分布式事务一致性风险：拆分后原单体事务变为分布式事务，需引入 Saga 或 TCC 模式。")
    if "Event-Driven" in recommended_style:
        risks.append("事件顺序和幂等性风险：异步消息可能乱序或重复投递，消费者需实现幂等处理。")
    feats = features or {}
    if feats.get("strict_consistency"):
        risks.append("强一致性破坏风险：不要盲目拆分核心事务边界，保持 ACID 事务在单个服务内完成。")
    if feats.get("security"):
        risks.append("权限和审计衔接风险：重构后的服务需重新集成认证授权体系，确保审计日志不中断。")
    if not risks:
        risks.append("团队技能适应风险：新架构模式的学习曲线可能导致短期效率下降。")

    mitigation = []
    if "Microservices" in recommended_style:
        mitigation.append("采用 Saga 编排模式管理跨服务事务，避免分布式两阶段提交。")
        mitigation.append("引入服务网格（Istio/Linkerd）管理服务间通信、重试和熔断。")
    if feats.get("security"):
        mitigation.append("建立统一的 API 网关认证中心，所有服务均通过 OAuth2.0/OIDC 进行身份验证。")
        mitigation.append("审计日志统一收集到集中式日志平台（ELK/Loki），确保可追溯。")
    mitigation.append("建立重构监控看板，跟踪迁移进度、错误率和延迟指标。")

    return {
        "refactoring_needed": refactoring_needed,
        "detected_architecture_smells": [
            {"name_zh": s["name_zh"], "description": s["description"]} for s in smells
        ],
        "target_architecture": target,
        "target_architecture_zh": target_zh,
        "suggested_patterns": [
            {"name": p["name"], "name_zh": p["name_zh"], "when": p["when"]} for p in patterns
        ],
        "migration_steps": migration_steps,
        "risks": risks,
        "mitigation_suggestions": mitigation,
    }


# ── LLM 润色 (可选) ───────────────────────────────────────────

async def llm_polish(requirement: str, rule_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """LLM 润色重构建议的迁移步骤和风险描述."""
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL):
        return None

    prompt = (
        "你是一位软件架构重构专家。以下是一个架构重构建议的初稿，请润色其迁移步骤和风险描述，"
        "使其更具体、更有工程可操作性。保持原有结构，只改进表述质量。\n\n"
        f"原始需求：{requirement}\n"
        f"规则生成的建议：{json.dumps(rule_result, ensure_ascii=False)}\n\n"
        "返回严格的 JSON 格式，字段与输入相同，仅润色 migration_steps 和 risks 和 mitigation_suggestions。"
    )

    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a software refactoring expert. Output only JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"].strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0]
            polished = json.loads(raw_text)
            logger.info("LLM polished refactoring advice")
            return polished
    except Exception as e:
        logger.warning(f"LLM polish failed (using rule template): {e}")
        return None


# ── API 端点 ──────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "refactoring-agent"}


@app.post("/refactor")
async def refactor(payload: RefactorRequest) -> Dict[str, Any]:
    req = payload.requirement
    features = payload.features
    rec_style = payload.recommended_style
    rec_combo = payload.recommended_combination

    # 1. 规则引擎检测
    smells = detect_smells(req, features)
    patterns = select_patterns(req, features, rec_style)

    # 2. 生成规则模板
    rule_result = build_rule_template(req, smells, patterns, rec_style, rec_combo, features)

    # 3. LLM 润色 (可选)
    polished = await llm_polish(req, rule_result)
    if polished:
        if "migration_steps" in polished:
            rule_result["migration_steps"] = polished["migration_steps"]
        if "risks" in polished:
            rule_result["risks"] = polished["risks"]
        if "mitigation_suggestions" in polished:
            rule_result["mitigation_suggestions"] = polished["mitigation_suggestions"]
        rule_result["llm_polished"] = True
    else:
        rule_result["llm_polished"] = False

    logger.info(
        f"Refactoring analysis: needed={rule_result['refactoring_needed']}, "
        f"smells={len(smells)}, patterns={len(patterns)}, polished={rule_result['llm_polished']}"
    )
    return rule_result
