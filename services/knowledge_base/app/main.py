import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("knowledge-base")

app = FastAPI(title="Knowledge Base Service", version="0.1.0")
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "architecture_styles.json"


def load_styles() -> Dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_styles(data: Dict[str, Any]) -> None:
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class StylePayload(BaseModel):
    name: str
    tags: list[str]
    best_for: list[str]
    pros: list[str]
    cons: list[str]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "knowledge-base"}


@app.get("/styles")
def get_styles() -> Dict[str, Any]:
    return load_styles()


@app.post("/styles")
def add_style(payload: StylePayload) -> Dict[str, Any]:
    data = load_styles()
    styles = data.get("styles", [])
    styles.append(payload.model_dump())
    data["styles"] = styles
    save_styles(data)
    return {"status": "ok", "count": len(styles)}


# ————————————————————————————
# 案例学习：用户反馈接口
# ————————————————————————————

# 案例学习数据文件
FEEDBACK_PATH = Path(__file__).resolve().parent.parent / "data" / "feedback_log.json"
# 知识进化权重文件：{feature: {style: count}} —— 随反馈积累自动更新
WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "data" / "learned_weights.json"

# 与 requirements_agent 同步的特征词库, 用于从反馈文本中提取特征维度
_FEEDBACK_LEXICON: Dict[str, List[str]] = {
    "high_concurrency": ["高并发", "并发", "万人", "海量用户", "峰值", "秒杀", "高吞吐", "qps"],
    "real_time": ["实时", "即时", "在线", "低延迟", "毫秒", "消息", "通知", "im"],
    "reliability": ["可靠", "高可用", "容灾", "容错", "稳定", "不丢", "一致性"],
    "scalability": ["扩展", "弹性", "扩容", "横向", "scale", "可伸缩"],
    "complex_business": ["复杂业务", "交易", "审批", "规则", "工作流", "workflow"],
    "strict_consistency": ["强一致", "事务", "金融", "账务", "一致提交"],
    "deployment_constraint": ["本地部署", "私有化", "边缘", "多地域", "离线", "内网"],
    "data_intensive": ["数据流", "etl", "流处理", "日志", "监控", "数据中台", "批处理", "流水线", "管道", "图像处理"],
    "team_size_large": ["多团队", "多个团队", "跨团队", "多人协作", "并行开发"],
    "security": ["安全", "加密", "认证", "鉴权", "授权", "审计", "隔离", "防护", "合规", "脱敏", "权限"],
}


def _extract_features_from_requirement(text: str) -> List[str]:
    """从需求文本中提取触发的特征标签, 用于反馈权重学习."""
    text_lower = text.lower()
    active = []
    for feature, keywords in _FEEDBACK_LEXICON.items():
        if any(kw in text_lower for kw in keywords):
            active.append(feature)
    return active


def _load_weights() -> Dict[str, Dict[str, int]]:
    """加载学习权重: {feature_name: {style_name: count}}."""
    if WEIGHTS_PATH.exists():
        with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_weights(weights: Dict[str, Dict[str, int]]) -> None:
    """持久化学习权重到 JSON 文件."""
    with open(WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)


def _update_learned_weights(payload: FeedbackPayload) -> None:
    """知识进化核心：从用户反馈中提取特征, 更新特征-风格关联权重。
    用户确认(+1)或修正(用户选择+1)都会增强对应风格与需求特征的关联。
    积累的权重供 matching-agent 在评分时作为 "learned boost" 加分使用。
    """
    features = _extract_features_from_requirement(payload.requirement)
    if not features:
        return
    # 用户修正时用修正后的风格; 确认时用推荐风格(两者相同)
    target_style = payload.user_choice if payload.user_choice else payload.recommended_style
    weights = _load_weights()
    for feat in features:
        if feat not in weights:
            weights[feat] = {}
        weights[feat][target_style] = weights[feat].get(target_style, 0) + 1
    _save_weights(weights)
    logger.info(f"Learned weights updated: {len(features)} features -> {target_style}")


class FeedbackPayload(BaseModel):
    requirement: str
    recommended_style: str
    user_choice: Optional[str] = None   # 用户实际选择的风格
    comment: Optional[str] = None


@app.get("/feedback")
def get_feedback() -> Dict[str, Any]:
    """获取反馈记录列表."""
    if not FEEDBACK_PATH.exists():
        return {"feedback": [], "count": 0}
    with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"feedback": data, "count": len(data)}


@app.post("/feedback")
def add_feedback(payload: FeedbackPayload) -> Dict[str, Any]:
    """记录用户对架构推荐的反馈, 用于后续权重学习和案例积累."""
    feedback_list: List[Dict[str, Any]] = []
    if FEEDBACK_PATH.exists():
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            feedback_list = json.load(f)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "requirement": payload.requirement,
        "recommended_style": payload.recommended_style,
        "user_choice": payload.user_choice,
        "comment": payload.comment,
        "is_confirmed": payload.user_choice == payload.recommended_style,
    }
    feedback_list.append(entry)

    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(feedback_list, f, ensure_ascii=False, indent=2)

    # --- 知识进化：更新特征-风格关联权重 ---
    _update_learned_weights(payload)

    logger.info(f"Feedback recorded: {entry['recommended_style']} -> user: {entry['user_choice']}")
    return {"status": "ok", "total_feedback": len(feedback_list)}


@app.get("/feedback/stats")
def get_feedback_stats() -> Dict[str, Any]:
    """反馈统计: 准确率、各风格确认/修正分布."""
    if not FEEDBACK_PATH.exists():
        return {"total": 0, "accuracy": 0, "style_stats": {}}

    with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
        feedback_list = json.load(f)

    total = len(feedback_list)
    confirmed = sum(1 for e in feedback_list if e.get("is_confirmed"))
    accuracy = round(confirmed / total, 4) if total else 0.0

    # 按推荐风格统计
    style_stats: Dict[str, Dict[str, int]] = {}
    for entry in feedback_list:
        rec = entry.get("recommended_style", "unknown")
        if rec not in style_stats:
            style_stats[rec] = {"total": 0, "confirmed": 0}
        style_stats[rec]["total"] += 1
        if entry.get("is_confirmed"):
            style_stats[rec]["confirmed"] += 1

    return {
        "total": total,
        "accuracy": accuracy,
        "confirmed": confirmed,
        "style_stats": style_stats,
    }


@app.get("/feedback/weights")
def get_learned_weights() -> Dict[str, Any]:
    """获取学习权重, 供 matching-agent 在评分时使用."""
    weights = _load_weights()
    # 统计每个风格的总学习次数
    style_learn_counts: Dict[str, int] = {}
    for feat, style_map in weights.items():
        for style_name, count in style_map.items():
            style_learn_counts[style_name] = style_learn_counts.get(style_name, 0) + count
    return {
        "weights": weights,
        "total_feedback_learned": sum(style_learn_counts.values()),
        "style_learn_counts": style_learn_counts,
    }
