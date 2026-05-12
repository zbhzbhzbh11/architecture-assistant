import logging
import os
from pathlib import Path
from typing import Dict, List

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

# Auto-load .env if exists
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
logger = logging.getLogger("requirements-agent")

app = FastAPI(title="Requirements Agent", version="0.2.0")

LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

NEGATION_PATTERNS = ["不需要", "不要求", "无需", "不需要", "没有", "无高", "非"]


class ExtractRequest(BaseModel):
    requirement: str = Field(..., min_length=10)


class ExtractResponse(BaseModel):
    features: Dict[str, bool]
    feature_hits: Dict[str, List[str]]


def filter_negation(text: str, hits: List[str]) -> List[str]:
    """过滤被否定词修饰的关键词."""
    filtered = []
    for word in hits:
        idx = text.find(word)
        prefix = text[max(0, idx - 6):idx]
        if any(neg in prefix for neg in NEGATION_PATTERNS):
            continue
        filtered.append(word)
    return filtered


def keyword_hits(text: str, words: List[str]) -> List[str]:
    raw = [word for word in words if word in text]
    return filter_negation(text, raw)


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
}


async def llm_semantic_supplement(text: str, features: Dict[str, bool],
                                   feature_hits: Dict[str, List[str]]) -> Dict[str, bool]:
    """当规则命中维度 <= 2 时, 调 LLM 做语义补全. LLM 不可用时静默降级."""
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL):
        return features

    active_count = sum(1 for v in features.values() if v)
    if active_count > 2:
        return features

    logger.info(f"Rule hits only {active_count} dimensions, requesting LLM supplement...")
    zh_labels = ", ".join(FEATURE_LABELS_ZH.values())
    prompt = (
        "分析以下软件需求描述, 判断是否涉及这些特征维度: "
        f"{zh_labels}。"
        "返回严格的 JSON 格式: {\"特征名\": true/false}, 不要输出其他内容。"
        f"\n\n需求: {text}"
    )
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a requirements analyst. Output only JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            resp = await client.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"].strip()
            # 尝试解析 JSON
            import json
            # 去掉可能的 markdown 代码块包裹
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0]
            llm_result = json.loads(raw_text)
            # 回写 LLM 推断的特征 (只写 True, 不覆盖已有 True)
            for zh_name, flag in llm_result.items():
                eng_key = {v: k for k, v in FEATURE_LABELS_ZH.items()}.get(zh_name)
                if eng_key and flag and not features.get(eng_key):
                    features[eng_key] = True
                    feature_hits[eng_key] = feature_hits.get(eng_key, []) + ["llm_supplement"]
            logger.info(f"LLM supplement added features: {sum(1 for v in features.values() if v)} total")
    except Exception as e:
        logger.warning(f"LLM supplement failed (fallback to rule-only): {e}")
    return features


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "requirements-agent"}


@app.post("/extract", response_model=ExtractResponse)
async def extract(payload: ExtractRequest) -> ExtractResponse:
    logger.info(f"Extracting features from requirement: {payload.requirement[:50]}...")
    text = payload.requirement.lower()

    lexicon: Dict[str, List[str]] = {
        "high_concurrency": [
            "高并发",
            "并发",
            "万人",
            "海量用户",
            "峰值",
            "秒杀",
            "高吞吐",
            "高qps",
            "qps",
            "concurrent",
        ],
        "real_time": [
            "实时",
            "实时性",
            "即时",
            "在线",
            "低延迟",
            "毫秒",
            "消息",
            "通知",
            "im",
            "real-time",
        ],
        "reliability": [
            "可靠",
            "可靠性",
            "高可用",
            "容灾",
            "容错",
            "稳定",
            "不丢",
            "一致性",
            "reliable",
        ],
        "scalability": [
            "扩展",
            "扩展性",
            "可扩展",
            "扩容",
            "弹性",
            "弹性扩缩",
            "横向",
            "scale",
            "可伸缩",
        ],
        "complex_business": [
            "复杂业务",
            "交易",
            "审批",
            "规则",
            "工作流",
            "workflow",
            "多流程",
        ],
        "strict_consistency": [
            "强一致",
            "事务",
            "金融",
            "账务",
            "一致提交",
        ],
        "deployment_constraint": [
            "本地部署",
            "私有化",
            "边缘",
            "多地域",
            "离线",
            "内网",
        ],
        "data_intensive": [
            "数据流",
            "etl",
            "流处理",
            "日志",
            "监控",
            "数据中台",
            "批处理",
            "流水线",
            "管道",
            "图像处理",
        ],
        "team_size_large": [
            "多团队",
            "多个团队",
            "跨团队",
            "多人协作",
            "团队协作",
            "并行开发",
        ],
        "security": [
            "安全",
            "加密",
            "认证",
            "鉴权",
            "授权",
            "审计",
            "隔离",
            "防护",
            "合规",
            "脱敏",
            "防篡改",
            "权限",
            "安全隔离",
            "可靠交付",
            "零信任",
        ],
    }

    feature_hits = {name: keyword_hits(text, words) for name, words in lexicon.items()}
    features = {name: len(hits) > 0 for name, hits in feature_hits.items()}

    # LLM 语义补全: 规则命中过少时调 LLM 二次分析
    features = await llm_semantic_supplement(text, features, feature_hits)

    return ExtractResponse(features=features, feature_hits=feature_hits)
