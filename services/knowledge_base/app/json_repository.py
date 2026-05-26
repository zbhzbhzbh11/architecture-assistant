"""JSON 文件存储层 — 知识库的 fallback 实现和冷备存储.

【模块功能】
当 Neo4j 不可用或 BACKEND=json 时, 从此层读取全部知识库数据。
同时提供特征提取和权重更新功能, 供 GraphRepository 调用。

【存储位置】
  architecture_styles.json     — 10 种架构风格元数据
  feedback_log.json           — 用户反馈原始记录 (冷备)
  learned_weights.json        — 学习权重缓存 (Neo4j 重算后覆写于此)
  architecture_combinations.json — 5 种架构组合模式
  adr_records.json            — 架构决策记录

【与 GraphRepository 的关系】
  - 所有 REST API 通过 _repo() 调度到此层 (BACKEND=json 时直接调用,
    BACKEND=auto 时作为 Neo4j 的 fallback)
  - add_feedback() 被 GraphRepository 调用做冷备
  - _update_learned_weights() 从需求文本提取特征并更新权重计数
  - _extract_features_from_requirement() 被 GraphRepository 复用
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("knowledge-base.json")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STYLES_PATH = DATA_DIR / "architecture_styles.json"
FEEDBACK_PATH = DATA_DIR / "feedback_log.json"
WEIGHTS_PATH = DATA_DIR / "learned_weights.json"

# ═══════════════════════════════════════════════════════════════
# 中文关键词词典 — 从需求文本中提取 10 维特征
# 与 requirements_agent 的 lexicon 保持一致
# ═══════════════════════════════════════════════════════════════
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


class JsonRepository:
    """JSON 文件存储实现 — 与 GraphRepository 接口一致."""

    @staticmethod
    def get_styles() -> Dict[str, Any]:
        with open(STYLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def add_style(payload: Dict[str, Any]) -> int:
        data = JsonRepository.get_styles()
        styles = data.get("styles", [])
        styles.append(payload)
        data["styles"] = styles
        with open(STYLES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return len(styles)

    # ── 反馈 ──────────────────────────────────────────────────

    @staticmethod
    def get_feedback() -> Dict[str, Any]:
        """获取反馈列表."""
        if not FEEDBACK_PATH.exists():
            return {"feedback": [], "count": 0}
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"feedback": data, "count": len(data)}

    @staticmethod
    def add_feedback(requirement: str, recommended_style: str,
                     user_choice: Optional[str], comment: Optional[str]) -> Dict[str, Any]:
        """记录一条反馈并触发权重学习."""
        feedback_list: List[Dict[str, Any]] = []
        if FEEDBACK_PATH.exists():
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                feedback_list = json.load(f)

        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "requirement": requirement,
            "recommended_style": recommended_style,
            "user_choice": user_choice,
            "comment": comment,
            "is_confirmed": user_choice == recommended_style,
        }
        feedback_list.append(entry)

        with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=2)

        _update_learned_weights(requirement, user_choice or recommended_style)
        logger.info(f"JSON feedback recorded: {recommended_style} -> user: {user_choice}")
        return {"status": "ok", "total_feedback": len(feedback_list)}

    @staticmethod
    def get_feedback_stats() -> Dict[str, Any]:
        """反馈统计."""
        if not FEEDBACK_PATH.exists():
            return {"total": 0, "accuracy": 0, "style_stats": {}}

        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            feedback_list = json.load(f)

        total = len(feedback_list)
        confirmed = sum(1 for e in feedback_list if e.get("is_confirmed"))
        accuracy = round(confirmed / total, 4) if total else 0.0

        style_stats: Dict[str, Dict[str, int]] = {}
        for entry in feedback_list:
            rec = entry.get("recommended_style", "unknown")
            if rec not in style_stats:
                style_stats[rec] = {"total": 0, "confirmed": 0}
            style_stats[rec]["total"] += 1
            if entry.get("is_confirmed"):
                style_stats[rec]["confirmed"] += 1

        return {"total": total, "accuracy": accuracy, "confirmed": confirmed, "style_stats": style_stats}

    @staticmethod
    def get_learned_weights() -> Dict[str, Any]:
        """获取学习权重 — 返回归一化值供 score_style 使用 + raw_weights 供前端展示."""
        raw = _load_weights()
        # 特征级 max-normalization
        normalized = {}
        for feat, style_map in raw.items():
            if style_map and max(style_map.values()) > 0:
                m = max(style_map.values())
                normalized[feat] = {s: c / m for s, c in style_map.items()}
            else:
                normalized[feat] = dict(style_map)
        style_learn_counts: Dict[str, int] = {}
        for feat, style_map in raw.items():
            for style_name, count in style_map.items():
                style_learn_counts[style_name] = style_learn_counts.get(style_name, 0) + count
        return {
            "weights": normalized,
            "raw_weights": raw,
            "total_feedback_learned": sum(style_learn_counts.values()),
            "style_learn_counts": style_learn_counts,
        }

    @staticmethod
    def reset_learned_weights() -> Dict[str, Any]:
        """重置学习权重为空."""
        _save_weights({})
        return {"status": "ok", "message": "learned_weights reset"}

    @staticmethod
    def graph_status() -> Dict[str, Any]:
        """JSON 后端没有图统计, 返回基本信息."""
        data = JsonRepository.get_styles()
        return {
            "backend": "json",
            "neo4j_available": False,
            "node_count": len(data.get("styles", [])),
            "relationship_count": 0,
        }

    # ── 架构组合 ────────────────────────────────────────────────

    _COMBO_PATH = DATA_DIR / "architecture_combinations.json"

    @classmethod
    def get_combinations(cls) -> Dict[str, Any]:
        """返回架构组合模式列表."""
        if not cls._COMBO_PATH.exists():
            return {"combinations": []}
        with open(cls._COMBO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── ADR (Architecture Decision Record) ──────────────────────

    _ADR_PATH = DATA_DIR / "adr_records.json"

    @classmethod
    def add_adr(cls, adr_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存 ADR 到 JSON 文件, 返回保存结果."""
        records: List[Dict[str, Any]] = []
        if cls._ADR_PATH.exists():
            with open(cls._ADR_PATH, "r", encoding="utf-8") as f:
                records = json.load(f)

        # 生成 ADR ID
        adr_id = f"ADR-{datetime.now().strftime('%Y%m%d')}-{len(records) + 1:03d}"
        adr_data["adr_id"] = adr_id
        adr_data["timestamp"] = adr_data.get("timestamp") or datetime.now().isoformat(timespec="seconds")
        records.append(adr_data)

        with open(cls._ADR_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        logger.info(f"ADR saved: {adr_id}")
        return {"adr_id": adr_id, "total": len(records), "status": "ok"}

    @classmethod
    def get_adrs(cls, limit: int = 20) -> Dict[str, Any]:
        """获取 ADR 列表."""
        if not cls._ADR_PATH.exists():
            return {"adrs": [], "total": 0}
        with open(cls._ADR_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
        return {"adrs": records[-limit:], "total": len(records)}

    @classmethod
    def get_adr(cls, adr_id: str) -> Optional[Dict[str, Any]]:
        """获取单条 ADR."""
        if not cls._ADR_PATH.exists():
            return None
        with open(cls._ADR_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
        for r in records:
            if r.get("adr_id") == adr_id:
                return r
        return None


# ── 内部辅助函数 ──────────────────────────────────────────────


def _load_weights() -> Dict[str, Dict[str, int]]:
    if WEIGHTS_PATH.exists():
        with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_weights(weights: Dict[str, Dict[str, int]]) -> None:
    with open(WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)


def _extract_features_from_requirement(text: str) -> List[str]:
    text_lower = text.lower()
    active = []
    for feature, keywords in _FEEDBACK_LEXICON.items():
        if any(kw in text_lower for kw in keywords):
            active.append(feature)
    return active


def _update_learned_weights(requirement: str, target_style: str) -> None:
    features = _extract_features_from_requirement(requirement)
    if not features:
        return
    weights = _load_weights()
    for feat in features:
        if feat not in weights:
            weights[feat] = {}
        weights[feat][target_style] = weights[feat].get(target_style, 0) + 1
    _save_weights(weights)
    logger.info(f"Learned weights updated: {len(features)} features -> {target_style}")
