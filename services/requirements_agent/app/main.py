"""Requirements Agent — LLM 语义理解 + 词典溯源.

【模块功能】
LLM 独立分析需求文本, 输出 12 维特征 + 架构分析理由。
词典仅用于补充关键词证据 (可解释性), 不影响判断结果。

【为什么 LLM 优先】
1. 自然语言千变万化 — "双十一流量"/"日活百万"/"并发极高" LLM 都能理解
2. 否定语义 LLM 原生支持 — 不需要手工维护否定词列表和窗口参数
3. 词典降级为"证据库" — 只回答"为什么", 不决定"是什么"
4. LLM 不可用时回退纯规则模式

【流程】
  Phase 1: LLM 独立分析 → 12维判断 + 架构倾向
  Phase 2: 词典溯源 → 为 LLM 判断的特征补充关键词证据
  Phase 3: 回退 → LLM 不可用时降级纯规则提取
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

# ── 本地开发: 将 services/ 加入 sys.path ──
_SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

# ── .env 自动加载 (Docker 中通过 docker-compose 注入, 本地开发用此回退) ──
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

# ── 日志 ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("requirements-agent")

app = FastAPI(title="Requirements Agent", version="0.3.0")

# ═══════════════════════════════════════════════════════════════
# 词典加载 — 优先读取外置 JSON, 回退硬编码
# ═══════════════════════════════════════════════════════════════
_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "data" / "feature_lexicon.json"


def _load_lexicon() -> Dict[str, List[str]]:
    """加载特征关键词词典 — JSON 优先, 不可用时用硬编码回退."""
    import json as _json

    # 尝试 JSON 文件
    json_paths = [
        _LEXICON_PATH,
        Path("/app/knowledge_base/data/feature_lexicon.json"),
        Path("/app/data/feature_lexicon.json"),
    ]
    for path in json_paths:
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            lex = data.get("lexicon", data)
            if isinstance(lex, dict) and len(lex) >= 12:
                logger.info(f"Lexicon loaded from {path} ({sum(len(v) for v in lex.values())} keywords)")
                return {k: [str(w).lower() for w in v] for k, v in lex.items()}
        except Exception:
            continue

    # 硬编码回退
    logger.warning("No lexicon JSON found, using hardcoded fallback")
    return {
        "high_concurrency": ["高并发", "并发", "万人", "海量用户", "峰值", "秒杀", "高吞吐", "高qps", "qps", "concurrent", "高负载", "大流量"],
        "real_time": ["实时", "实时性", "即时", "在线", "低延迟", "毫秒", "消息", "通知", "im", "real-time", "推送", "同步"],
        "reliability": ["可靠", "可靠性", "高可用", "容灾", "容错", "稳定", "不丢", "一致性", "reliable", "灾备", "熔断", "sla"],
        "scalability": ["扩展", "扩展性", "可扩展", "扩容", "弹性", "弹性扩缩", "横向", "scale", "可伸缩", "水平扩展", "集群", "分片"],
        "complex_business": ["复杂业务", "交易", "审批", "规则", "工作流", "workflow", "多流程", "内容管理", "栏目", "文章发布", "cms", "多级栏目", "多模块", "erp", "面向对象", "领域模型", "领域驱动", "ddd", "规则引擎", "决策表", "风控引擎", "核保", "反欺诈", "定价策略", "规则库", "业务规则"],
        "strict_consistency": ["强一致", "事务", "金融", "账务", "一致提交", "原子性", "acid", "转账", "回滚", "分布式事务"],
        "deployment_constraint": ["本地部署", "私有化", "边缘", "多地域", "离线", "内网", "私有云", "信创", "国产化", "不能联网", "局域网"],
        "data_intensive": ["数据流", "etl", "流处理", "日志", "监控", "数据中台", "批处理", "批量", "离线处理", "定时任务", "日终", "流水线", "管道", "大数据", "数据仓库", "数据湖", "数仓", "数据平台", "离线分析", "bi", "报表", "tb级", "pb级"],
        "team_size_large": ["多团队", "多个团队", "跨团队", "多人协作", "团队协作", "并行开发", "多部门", "外包", "协作开发", "独立交付"],
        "security": ["安全", "加密", "认证", "鉴权", "授权", "审计", "隔离", "防护", "合规", "脱敏", "防篡改", "权限", "安全隔离", "零信任", "等保", "隐私", "gdpr", "风控"],
    "simple_crud": ["增删改查", "crud", "内部工具", "管理后台", "表单录入", "展示为主", "简单系统", "不复杂", "纯查询"],
    "resource_constrained": ["预算有限", "成本控制", "小团队", "快速交付", "mvp", "原型验证", "不想维护", "免运维", "初创团队", "资源受限"],
    }

LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()


class ExtractRequest(BaseModel):
    requirement: str = Field(..., min_length=5)


ARCH_STYLE_NAMES = [
    "Layered Architecture", "Microservices", "Event-Driven Architecture",
    "SOA", "Hexagonal Architecture", "Pipeline-Filter", "CQRS",
    "Serverless", "Space-Based", "Client-Server",
]


class ExtractResponse(BaseModel):
    features: Dict[str, bool]
    feature_hits: Dict[str, List[str]]
    llm_disputed: Dict[str, bool] = {}
    arch_inclination: Dict[str, Any] = {}


FEATURE_LABELS_ZH = {
    "high_concurrency": "高并发",
    "real_time": "实时性",
    "reliability": "可靠性",
    "scalability": "可扩展性",
    "complex_business": "复杂业务",
    "strict_consistency": "强一致性",
    "deployment_constraint": "部署约束",
    "data_intensive": "数据密集型",
    "team_size_large": "多团队协作",
    "security": "安全性",
    "simple_crud": "极简业务",
    "resource_constrained": "资源受限",
}


async def llm_analyze(text: str) -> Tuple[Dict[str, bool], Dict[str, Any]]:
    """Phase 1: LLM 独立分析 — 不受规则引擎影响，自主判断全部 12 维特征。

    Returns:
        (features, arch_inclination)
        features: 12维 bool 字典
        arch_inclination: 架构倾向 {complexity_hint, arch_avoid, arch_prefer, reason}
    """
    features = {eng: False for eng in FEATURE_LABELS_ZH}
    arch_inclination: Dict[str, Any] = {}

    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL):
        logger.info("LLM not configured, will use rule-only fallback")
        raise RuntimeError("LLM not configured")

    arch_names = ", ".join(ARCH_STYLE_NAMES)
    zh_labels = ", ".join(FEATURE_LABELS_ZH.values())

    arch_instruction = (
        "\n\n【架构倾向判断】基于需求文本直接判断系统复杂度和架构方向。"
        "输出 JSON (无法判断时输出 null):\n"
        '{"complexity_hint": "low/medium/high", '
        '"arch_avoid": ["应避免的架构"], '
        '"arch_prefer": ["倾向的架构"], '
        '"reason": "简短理由"}\n'
        f"可选架构: {arch_names}\n"
        "将特征JSON和架构JSON用 \"---ARCH---\" 分隔。"
    )

    try:
        from common.prompts.requirements_few_shot import build_few_shot_prompt
        prompt = build_few_shot_prompt(text) + arch_instruction
        logger.info("Using few-shot prompt for LLM analysis")
    except ImportError:
        logger.info("Few-shot not available, using zero-shot prompt")
        prompt = (
            "你是一位资深软件架构分析师。仔细阅读以下需求描述，对每个维度独立判断。\n"
            "注意：识别否定语义 (\"不需要实时\" → 实时性=false)。"
            "识别隐含特征 (\"双十一流量\" → 高并发=true)。\n"
            f"维度定义: {zh_labels}。\n"
            "返回严格的 JSON: {\"特征名\": true/false}，每个维度都必须输出。"
            f"\n\n需求: {text}"
        ) + arch_instruction

    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": (
                "You are a senior software architecture analyst. "
                "Analyze requirements independently for each dimension. "
                "Understand implicit signals (\"Double-11 traffic\" implies high concurrency). "
                "Respect negation (\"doesn't need real-time\" means real_time=false). "
                "Do NOT let a single keyword override the overall meaning. "
                "Output only valid JSON."
            )},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"].strip()
        import json as _json
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0]

        # 分离特征 JSON 和架构倾向 JSON
        if "---ARCH---" in raw_text:
            parts = raw_text.split("---ARCH---", 1)
            feature_json = parts[0].strip()
            arch_json = parts[1].strip()
            if arch_json and arch_json.lower() != "null":
                try:
                    parsed = _json.loads(arch_json)
                    if isinstance(parsed, dict):
                        arch_inclination = parsed
                except _json.JSONDecodeError:
                    pass
        else:
            feature_json = raw_text

        llm_result = _json.loads(feature_json)

        # 映射中文标签 → 英文 key
        reverse_map = {v: k for k, v in FEATURE_LABELS_ZH.items()}
        active_count = 0
        for zh_name, flag in llm_result.items():
            eng_key = reverse_map.get(zh_name)
            if eng_key and flag:
                features[eng_key] = True
                active_count += 1

        logger.info(f"LLM analysis: {active_count}/10 dimensions active, "
                    f"arch_inclination={'yes' if arch_inclination else 'no'}")

    return features, arch_inclination


def rule_extract(text: str, lexicon: Dict[str, List[str]]) -> Tuple[Dict[str, bool], Dict[str, List[str]]]:
    """Phase 3 回退: 纯规则提取 — LLM 不可用时的降级路径。

    关键词匹配 + 否定过滤, 保证核心功能在任何环境下都能运行。
    """
    NEGATION_WORDS = ["不需要", "不要求", "无需", "没有", "不涉及", "不支持", "不包含", "不应", "不必"]

    def _match_with_negation(words):
        hits = [w for w in words if w in text]
        # 双向否定检测
        result = []
        for w in hits:
            idx = text.find(w)
            ctx_start = max(0, idx - 8)
            ctx_end = min(len(text), idx + len(w) + 10)
            ctx = text[ctx_start:ctx_end]
            if not any(neg in ctx for neg in NEGATION_WORDS):
                result.append(w)
        return result

    feature_hits = {name: _match_with_negation(words) for name, words in lexicon.items()}
    features = {name: len(hits) > 0 for name, hits in feature_hits.items()}
    logger.info(f"Rule-only extraction: {sum(1 for v in features.values() if v)}/{len(features)} dimensions")
    return features, feature_hits


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "requirements-agent"}


# ═══════════════════════════════════════════════════════════════
# 主端点 — 特征提取三阶段完整流程
# ═══════════════════════════════════════════════════════════════

@app.post("/extract", response_model=ExtractResponse)
async def extract(payload: ExtractRequest) -> ExtractResponse:
    """从自然语言需求中提取 12 维结构化特征.

    Phase 1: LLM 独立分析 (主路径)
    Phase 2: 词典溯源 (为 LLM 判断补充关键词证据)
    Phase 3: 纯规则回退 (LLM 不可用时)
    """
    logger.info(f"Extracting features from requirement: {payload.requirement[:50]}...")
    text = payload.requirement.lower()
    lexicon: Dict[str, List[str]] = _load_lexicon()

    arch_inclination: Dict[str, Any] = {}
    llm_disputed: Dict[str, bool] = {}

    try:
        # Phase 1: LLM 独立分析
        features, arch_inclination = await llm_analyze(text)

        # Phase 2: 词典溯源 — 只为 LLM 标记的 True 特征找关键词证据
        feature_hits: Dict[str, List[str]] = {}
        for eng_key, is_active in features.items():
            if is_active:
                words = lexicon.get(eng_key, [])
                hits = [w for w in words if w in text]
                feature_hits[eng_key] = hits if hits else ["llm_identified"]
            else:
                feature_hits[eng_key] = []

        # LLM 返回 0 特征时, 合并规则提取结果 (LLM 语义理解可能有盲区)
        if sum(1 for v in features.values() if v) == 0:
            rule_features, rule_hits = rule_extract(text, lexicon)
            for k, v in rule_features.items():
                if v:
                    features[k] = True
                    feature_hits[k] = rule_hits.get(k, [])
                    logger.info(f"Rule supplement: {k} (LLM missed)")

        logger.info(f"LLM analysis complete: {sum(1 for v in features.values() if v)}/{len(features)} features")

    except Exception as e:
        # Phase 3: LLM 不可用 → 纯规则回退
        logger.warning(f"LLM unavailable, falling back to rule-only: {e}")
        features, feature_hits = rule_extract(text, lexicon)
        arch_inclination = {}

    return ExtractResponse(features=features, feature_hits=feature_hits,
                           llm_disputed=llm_disputed, arch_inclination=arch_inclination)
