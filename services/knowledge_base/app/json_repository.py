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
LEXICON_PATH = DATA_DIR / "feature_lexicon.json"


def _load_lexicon() -> Dict[str, List[str]]:
    """从 feature_lexicon.json 加载关键词词典 (12 维, 与 requirements_agent 同源)."""
    if LEXICON_PATH.exists():
        with open(LEXICON_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("lexicon", {})
    return {}


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
                     user_choice: Optional[str], comment: Optional[str],
                     features: Optional[Dict[str, bool]] = None,
                     rating: Optional[int] = None) -> Dict[str, Any]:
        """记录一条反馈并触发权重学习.
        features: LLM 已提取的 12 维特征 (优先使用)."""
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

        _update_learned_weights(requirement, user_choice or recommended_style, features)
        logger.info(f"JSON feedback recorded: {recommended_style} -> user: {user_choice}")
        return {"status": "ok", "total_feedback": len(feedback_list)}

    @staticmethod
    def _save_feedback_log(requirement: str, recommended_style: str,
                           user_choice: Optional[str], comment: Optional[str]) -> None:
        """冷备: 仅写入反馈日志, 不触发权重计算 (权重以 Neo4j 为权威源)."""
        feedback_list: List[Dict[str, Any]] = []
        if FEEDBACK_PATH.exists():
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                feedback_list = json.load(f)
        feedback_list.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "requirement": requirement,
            "recommended_style": recommended_style,
            "user_choice": user_choice,
            "comment": comment,
            "is_confirmed": user_choice == recommended_style,
        })
        with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=2)

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

    # ── 图谱风险 (JSON fallback) ──────────────────────────────────

    _RISK_MAP: Dict[str, Dict[str, List[str]]] = {
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
        "SOA": {
            "main_risks": ["ESB总线可能成为性能瓶颈",
                           "治理机制繁重增加开发开销",
                           "服务粒度划分困难容易导致过度拆分或欠拆分"],
            "suggestions": ["提前规划ESB扩容与高可用方案",
                            "定义清晰的服务契约与版本管理策略",
                            "引入轻量级集成层简化通信"],
        },
        "Hexagonal Architecture": {
            "main_risks": ["学习曲线较陡团队上手成本高",
                           "样板代码较多增加维护负担",
                           "简单CRUD场景存在过度设计风险"],
            "suggestions": ["从核心领域层开始逐步向外扩展",
                            "通过代码生成减少端口-适配器样板代码",
                            "定期评审架构边界避免抽象泄漏"],
        },
        "Pipeline-Filter": {
            "main_risks": ["分布式管道调试复杂定位困难",
                           "阶段间状态传递有额外性能开销",
                           "单个过滤器故障可能导致级联失败"],
            "suggestions": ["建立统一的结构化日志采集与追踪",
                            "定义标准化的阶段间数据格式减少转换开销",
                            "为每个过滤器设置独立健康检查和超时熔断"],
        },
        "CQRS": {
            "main_risks": ["读写模型同步复杂度高",
                           "系统整体复杂度显著增加需额外维护两套模型",
                           "最终一致性窗口期可能影响用户体验"],
            "suggestions": ["从单库起逐步拆分读写模型（渐进式CQRS）",
                            "引入事件溯源或CDC机制保证同步",
                            "明确标注哪些查询走最终一致性供前端处理"],
        },
        "Serverless": {
            "main_risks": ["云供应商锁定风险",
                           "冷启动延迟影响用户体验",
                           "执行时间限制不适合长任务，分布式函数调试困难"],
            "suggestions": ["抽象云厂商接口避免深度绑定",
                            "配置预置并发保持函数热启动",
                            "混合使用容器承载长时任务仅事件触发走Serverless"],
        },
        "Space-Based": {
            "main_risks": ["分布式一致性模型复杂",
                           "内存成本较高不适合大规模持久化场景",
                           "内存中数据在持久化前存在丢失风险"],
            "suggestions": ["配置异步写穿策略保证数据持久化",
                            "设计数据淘汰与分页策略控制内存占用",
                            "实现跨节点数据冗余降低单点风险"],
        },
        "Client-Server": {
            "main_risks": ["服务器端可能成为集中式性能瓶颈",
                           "弹性扩展能力有限不适合极端并发场景",
                           "客户端升级维护成本高"],
            "suggestions": ["增加负载均衡与集群化部署提升容量",
                            "使用CDN卸载静态资源请求减轻服务器压力",
                            "建立客户端自动更新机制降低运维成本"],
        },
    }

    @staticmethod
    def graph_risks(style_name: str) -> Dict[str, Any]:
        """JSON 回退: 从 _RISK_MAP 查询风险."""
        entry = JsonRepository._RISK_MAP.get(style_name)
        if entry:
            return {"style": style_name, "main_risks": entry["main_risks"],
                    "suggestions": entry["suggestions"]}
        return {"style": style_name, "main_risks": [
            "架构复杂度与需求规模不匹配的风险",
            "开发和运维团队对选定架构的熟悉程度",
            "后续演进中架构腐化的可能性",
        ], "suggestions": [
            "持续记录架构决策（ADR）并定期评审",
            "建立技术债务看板，规划重构窗口",
            "引入架构适配度度量指标并自动化检查",
        ]}

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

    @staticmethod
    def adr_stats() -> Dict[str, Any]:
        """JSON fallback: 从 adr_records.json 统计决策数据."""
        from collections import Counter
        path = JsonRepository._ADR_PATH
        if not path.exists():
            return {"total_decisions": 0, "style_stats": [], "feature_style_stats": []}
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        style_counter = Counter()
        feat_style_counter = Counter()
        for r in records:
            style = r.get("recommended_style", "")
            if style:
                style_counter[style] += 1
            features = r.get("extracted_features", {})
            for feat, val in features.items():
                if val and style:
                    feat_style_counter[(feat, style)] += 1
        style_stats = [{"style": s, "count": c}
                       for s, c in style_counter.most_common()]
        feat_stats = [{"feature": k[0], "style": k[1], "count": v}
                      for k, v in feat_style_counter.most_common(20)]
        return {"total_decisions": len(records), "style_stats": style_stats,
                "feature_style_stats": feat_stats}


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
    lexicon = _load_lexicon()
    active = []
    for feature, keywords in lexicon.items():
        if any(kw in text_lower for kw in keywords):
            active.append(feature)
    return active


def _update_learned_weights(requirement: str, target_style: str,
                             llm_features: Optional[Dict[str, bool]] = None) -> None:
    """更新学习权重 — 优先使用 LLM 提取的特征, fallback 到关键词提取."""
    if llm_features:
        active_features = [k for k, v in llm_features.items() if v]
    else:
        active_features = _extract_features_from_requirement(requirement)
    if not active_features:
        return
    weights = _load_weights()
    for feat in active_features:
        if feat not in weights:
            weights[feat] = {}
        weights[feat][target_style] = weights[feat].get(target_style, 0) + 1
    _save_weights(weights)
    source = "LLM" if llm_features else "keyword"
    logger.info(f"Learned weights updated ({source}): {len(active_features)} features -> {target_style}")
