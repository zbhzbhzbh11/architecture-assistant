"""Neo4j 图数据库存储层 —— 架构知识图谱的持久化和查询.

节点类型: ArchitectureStyle, QualityAttribute, Scenario, Risk
关系类型: HAS_QUALITY, SUITABLE_FOR, HAS_RISK, COMPLEMENTS

Neo4j 不可用时返回 None, 由上层 fallback 到 JSON.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("knowledge-base.graph")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687").strip()
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j").strip()
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j").strip()

# ── 时间衰减参数 ──────────────────────────────────────────
DECAY_K = 0.05  # e^(-0.05*days): 14天→50%, 30天→22%, 90天→1%


def _decay_weight(timestamp_str: Optional[str]) -> float:
    """计算一条反馈的时间衰减因子."""
    if not timestamp_str:
        return 1.0
    try:
        ts = datetime.fromisoformat(timestamp_str)
        days = max(0, (datetime.now(timezone.utc).replace(tzinfo=None) - ts).days)
        return math.exp(-DECAY_K * days)
    except (ValueError, TypeError):
        return 1.0


def _normalize_weights(raw: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """特征级 max-normalization: 每维度下除以最大值, 使值域 [0,1]."""
    result: Dict[str, Dict[str, float]] = {}
    for feat, style_map in raw.items():
        if not style_map:
            continue
        max_count = max(style_map.values())
        result[feat] = {style: count / max_count for style, count in style_map.items()} if max_count > 0 else dict(style_map)
    return result


def _get_driver():
    """获取 Neo4j driver, 连接失败返回 None."""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        logger.warning(f"Neo4j unavailable: {e}")
        return None


def _run_query(query: str, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
    """执行 Cypher 查询并返回记录列表."""
    driver = _get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    except Exception as e:
        logger.error(f"Neo4j query failed: {e}")
        return None
    finally:
        driver.close()


class GraphRepository:
    """Neo4j 图存储实现, 方法与 JsonRepository 保持一致."""

    # ── 架构风格 ──────────────────────────────────────────────

    @staticmethod
    def get_styles() -> Optional[Dict[str, Any]]:
        """从 Neo4j 查询全部风格并组装为 JSON 兼容格式."""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                # 查询所有风格及其关联的 quality attributes
                result = session.run("""
                    MATCH (s:ArchitectureStyle)
                    OPTIONAL MATCH (s)-[:HAS_QUALITY]->(q:QualityAttribute)
                    OPTIONAL MATCH (s)-[:SUITABLE_FOR]->(sc:Scenario)
                    OPTIONAL MATCH (s)-[:HAS_RISK]->(r:Risk)
                    RETURN s,
                           collect(DISTINCT q.name) AS qualities,
                           collect(DISTINCT sc.name) AS scenarios,
                           collect(DISTINCT r.name) AS risks
                """)
                styles = []
                for record in result:
                    s = record["s"]
                    style_data = dict(s)
                    # Neo4j 返回的节点属性不包含 name_zh 等扩展字段时用空值回退
                    style_data["tags"] = record["qualities"]
                    style_data["best_for"] = record["scenarios"]
                    style_data["best_for_zh"] = style_data.get("best_for_zh", [])
                    style_data["pros"] = style_data.get("pros", [])
                    style_data["pros_zh"] = style_data.get("pros_zh", [])
                    style_data["cons"] = style_data.get("cons", [])
                    style_data["cons_zh"] = style_data.get("cons_zh", [])
                    style_data["topology_mermaid"] = style_data.get("topology_mermaid", "")
                    style_data["name_zh"] = style_data.get("name_zh", style_data.get("name", ""))
                    # 将 JSON 字符串的 penalty_tags 转回 dict
                    if isinstance(style_data.get("penalty_tags"), str):
                        try:
                            style_data["penalty_tags"] = json.loads(style_data["penalty_tags"])
                        except Exception:
                            style_data["penalty_tags"] = {}
                    if "penalty_tags" not in style_data:
                        style_data["penalty_tags"] = {}
                    styles.append(style_data)

                if not styles:
                    return None  # 空图, 走 JSON fallback

            driver.close()
            return {"styles": styles}
        except Exception as e:
            logger.warning(f"Neo4j get_styles failed: {e}")
            return None

    @staticmethod
    def add_style(payload: Dict[str, Any]) -> Optional[int]:
        """在 Neo4j 中创建风格节点 + 关联节点."""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                # 创建风格节点
                import json as _json
                penalty_json = _json.dumps(payload.get("penalty_tags", {}), ensure_ascii=False)
                session.run("""
                    MERGE (s:ArchitectureStyle {name: $name})
                    SET s.name_zh = $name_zh,
                        s.topology_mermaid = $topo,
                        s.pros = $pros,
                        s.pros_zh = $pros_zh,
                        s.cons = $cons,
                        s.cons_zh = $cons_zh,
                        s.penalty_tags = $penalty_tags
                """, {
                    "name": payload.get("name", ""),
                    "name_zh": payload.get("name_zh", payload.get("name", "")),
                    "topo": payload.get("topology_mermaid", ""),
                    "pros": payload.get("pros", []),
                    "pros_zh": payload.get("pros_zh", []),
                    "cons": payload.get("cons", []),
                    "cons_zh": payload.get("cons_zh", []),
                    "penalty_tags": penalty_json,
                })
                # 创建 QualityAttribute 节点和关系
                for tag in payload.get("tags", []):
                    session.run("""
                        MERGE (q:QualityAttribute {name: $tag})
                        WITH q
                        MATCH (s:ArchitectureStyle {name: $style_name})
                        MERGE (s)-[:HAS_QUALITY]->(q)
                    """, {"tag": tag, "style_name": payload.get("name", "")})
                # 创建 Scenario 节点和关系
                for scenario in payload.get("best_for", []):
                    session.run("""
                        MERGE (sc:Scenario {name: $scenario})
                        WITH sc
                        MATCH (s:ArchitectureStyle {name: $style_name})
                        MERGE (s)-[:SUITABLE_FOR]->(sc)
                    """, {"scenario": scenario, "style_name": payload.get("name", "")})

                # 统计当前风格总数
                count_result = session.run("MATCH (s:ArchitectureStyle) RETURN count(s) AS cnt")
                count = count_result.single()["cnt"]
            driver.close()
            logger.info(f"Neo4j style added: {payload.get('name')}, total: {count}")
            return count
        except Exception as e:
            logger.warning(f"Neo4j add_style failed: {e}")
            return None

    # ── 反馈 ──────────────────────────────────────────────────

    @staticmethod
    def get_feedback() -> Optional[Dict[str, Any]]:
        """从 Neo4j 查询反馈列表."""
        rows = _run_query("""
            MATCH (f:Feedback)
            RETURN f
            ORDER BY f.timestamp DESC
        """)
        if rows is None:
            return None
        feedback = []
        for row in rows:
            f = dict(row["f"])
            feedback.append({
                "timestamp": f.get("timestamp", ""),
                "requirement": f.get("requirement", ""),
                "recommended_style": f.get("recommended_style", ""),
                "user_choice": f.get("user_choice"),
                "comment": f.get("comment"),
                "is_confirmed": f.get("is_confirmed", False),
            })
        return {"feedback": feedback, "count": len(feedback)}

    @staticmethod
    def add_feedback(requirement: str, recommended_style: str,
                     user_choice: Optional[str], comment: Optional[str]) -> Optional[Dict[str, Any]]:
        """保存反馈: Neo4j 为主存储, JSON 为冷备.
        Neo4j 不可用时返回 None 触发 _repo() fallback 到 JsonRepository."""
        # 1. Neo4j 存储 (主)
        try:
            total = GraphRepository._neo4j_save_feedback(
                requirement, recommended_style, user_choice, comment)
        except Exception as e:
            logger.warning(f"Neo4j feedback save failed, will fallback to JSON: {e}")
            return None

        # 2. JSON 备份
        try:
            from .json_repository import JsonRepository
            JsonRepository.add_feedback(requirement, recommended_style, user_choice, comment)
        except Exception as e:
            logger.warning(f"JSON feedback backup skipped: {e}")

        # 3. 从 Neo4j 重新计算权重并持久化到 learned_weights.json
        try:
            raw = GraphRepository._compute_weights_from_neo4j()
            normalized = _normalize_weights(raw)
            from .json_repository import _save_weights
            _save_weights(normalized)
            logger.info(f"Learned weights recomputed from Neo4j: {len(raw)} dims, normalized")
        except Exception as e:
            logger.warning(f"Weight recomputation from Neo4j failed: {e}")

        return {"status": "ok", "total_feedback": total}

    @staticmethod
    def get_feedback_stats() -> Optional[Dict[str, Any]]:
        """Neo4j 反馈统计."""
        rows = _run_query("MATCH (f:Feedback) RETURN f")
        if rows is None:
            return None

        feedback_list = [dict(r["f"]) for r in rows]
        total = len(feedback_list)
        if total == 0:
            return {"total": 0, "accuracy": 0, "style_stats": {}}

        confirmed = sum(1 for e in feedback_list if e.get("is_confirmed"))
        accuracy = round(confirmed / total, 4)

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
    def reset_learned_weights() -> Optional[Dict[str, Any]]:
        """Graph 模式下委托 JSON 后端重置权重 (权重仅存 JSON)."""
        return None  # 返回 None 触发 _repo() fallback 到 JSON

    @staticmethod
    def get_learned_weights() -> Optional[Dict[str, Any]]:
        """从 Neo4j 反馈数据直接计算学习权重 (Neo4j 为权威数据源).

        每条反馈的贡献 = 特征提取 × 时间衰减因子 e^(-0.05 × days).
        聚合后做特征级 max-normalization, 使不同特征的 bonus 可比.
        """
        from .json_repository import _extract_features_from_requirement

        # 查询全部反馈: requirement, recommended_style, timestamp
        rows = _run_query(
            "MATCH (f:Feedback) RETURN f.requirement AS requirement, "
            "f.recommended_style AS style, f.timestamp AS timestamp"
        )
        if rows is None:
            return None

        # 1. 聚合: 每条反馈加权衰减后累加到 raw 权重
        raw_weights: Dict[str, Dict[str, float]] = {}
        for row in rows:
            req = row.get("requirement", "")
            style = row.get("style", "")
            ts = row.get("timestamp")
            if not req or not style:
                continue
            features = _extract_features_from_requirement(req)
            decay = _decay_weight(ts)  # 时间衰减: 0~1
            for feat in features:
                raw_weights.setdefault(feat, {}).setdefault(style, 0.0)
                raw_weights[feat][style] += decay  # 不再 +1, 加衰减值

        # 2. 归一化: 每个特征维度下除以最大值
        normalized = _normalize_weights(raw_weights)

        # 3. 统计
        style_learn_counts: Dict[str, int] = {}
        for feat, style_map in raw_weights.items():
            for style_name, count in style_map.items():
                style_learn_counts[style_name] = style_learn_counts.get(style_name, 0) + int(count)

        return {
            "weights": normalized,            # float, 归一化后 → score_style 使用
            "raw_weights": raw_weights,       # float, 带衰减的原始值 → 前端表格展示
            "total_feedback_learned": sum(style_learn_counts.values()),
            "style_learn_counts": style_learn_counts,
        }

    # ── Neo4j 内部辅助 ──────────────────────────────────────────

    @staticmethod
    def _neo4j_save_feedback(requirement: str, recommended_style: str,
                             user_choice: Optional[str], comment: Optional[str]) -> int:
        """写入 Feedback 节点到 Neo4j, 返回总反馈数."""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                session.run("""
                    CREATE (f:Feedback {
                        timestamp: $ts, requirement: $req,
                        recommended_style: $rec, user_choice: $choice,
                        comment: $comment, is_confirmed: $confirmed
                    })
                """, {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "req": requirement, "rec": recommended_style,
                    "choice": user_choice, "comment": comment,
                    "confirmed": user_choice == recommended_style,
                })
                total = session.run("MATCH (f:Feedback) RETURN count(f) AS cnt").single()["cnt"]
            driver.close()
            return total
        except Exception as e:
            logger.warning(f"Neo4j feedback save failed: {e}")
            raise

    @staticmethod
    def _compute_weights_from_neo4j() -> Dict[str, Dict[str, float]]:
        """从 Neo4j Feedback 节点批量计算带衰减的 feature→style 原始权重.

        不包含归一化 — 调用方自行处理."""
        from .json_repository import _extract_features_from_requirement

        rows = _run_query(
            "MATCH (f:Feedback) RETURN f.requirement AS requirement, "
            "f.recommended_style AS style, f.timestamp AS timestamp"
        )
        if rows is None:
            return {}

        weights: Dict[str, Dict[str, float]] = {}
        for row in rows:
            req = row.get("requirement", "")
            style = row.get("style", "")
            ts = row.get("timestamp")
            if not req or not style:
                continue
            features = _extract_features_from_requirement(req)
            decay = _decay_weight(ts)
            for feat in features:
                weights.setdefault(feat, {}).setdefault(style, 0.0)
                weights[feat][style] += decay
        return weights

    @staticmethod
    def reset_learned_weights() -> Dict[str, Any]:
        """清空 Neo4j 中所有 Feedback 节点, 并重置 learned_weights.json."""
        _run_query("MATCH (f:Feedback) DETACH DELETE f")
        from .json_repository import _save_weights
        _save_weights({})
        logger.info("Learned weights reset: Neo4j + JSON cleared")
        return {"status": "ok", "message": "learned_weights reset"}

    @staticmethod
    def graph_match(features: Dict[str, bool]) -> Optional[Dict[str, Any]]:
        """基于 Neo4j 图谱关系匹配架构风格.

        对每个活跃特征, 查找具备该质量属性的风格节点, 同时拉取关联的场景、
        风险和可组合风格. 返回图谱证据供 matching-agent 融合评分.
        """
        active_features = [k for k, v in features.items() if v]
        if not active_features:
            return None

        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                style_scores: Dict[str, Dict[str, Any]] = {}

                for feat in active_features:
                    # 查找通过 HAS_QUALITY 关联到此 quality attribute 的架构风格
                    result = session.run("""
                        MATCH (q:QualityAttribute {name: $feat})
                        MATCH (s:ArchitectureStyle)-[:HAS_QUALITY]->(q)
                        OPTIONAL MATCH (s)-[:SUITABLE_FOR]->(sc:Scenario)
                        OPTIONAL MATCH (s)-[:HAS_RISK]->(r:Risk)
                        OPTIONAL MATCH (s)-[:COMPLEMENTS]->(c:ArchitectureStyle)
                        RETURN s.name AS style,
                               s.name_zh AS style_zh,
                               collect(DISTINCT q.name) AS qualities,
                               collect(DISTINCT sc.name) AS scenarios,
                               collect(DISTINCT r.name) AS risks,
                               collect(DISTINCT c.name) AS complements
                    """, {"feat": feat})

                    for record in result:
                        name = record["style"]
                        if name not in style_scores:
                            style_scores[name] = {
                                "style": name,
                                "style_zh": record["style_zh"] or name,
                                "graph_score": 0,
                                "matched_attributes": [],
                                "matched_scenarios": [],
                                "related_risks": [],
                                "combinable_styles": [],
                            }
                        entry = style_scores[name]
                        if feat not in entry["matched_attributes"]:
                            entry["matched_attributes"].append(feat)
                            entry["graph_score"] += 2  # 每个匹配的质量属性 +2
                        for sc in record["scenarios"]:
                            if sc and sc not in entry["matched_scenarios"]:
                                entry["matched_scenarios"].append(sc)
                        for risk in record["risks"]:
                            if risk and risk not in entry["related_risks"]:
                                entry["related_risks"].append(risk)
                        for comp in record["complements"]:
                            if comp and comp not in entry["combinable_styles"]:
                                entry["combinable_styles"].append(comp)

            driver.close()

            if not style_scores:
                return None

            # 按 graph_score 降序
            ranked = sorted(style_scores.values(), key=lambda x: x["graph_score"], reverse=True)
            return {
                "available": True,
                "active_features": active_features,
                "ranked": ranked,
            }
        except Exception as e:
            logger.warning(f"Neo4j graph_match failed: {e}")
            return None

    # ── 图谱评分 + 风险查询 (Phase 2 双驱动架构) ─────────────────

    @staticmethod
    def graph_score(features: Dict[str, bool]) -> Optional[Dict[str, Any]]:
        """一条 Cypher 完成 4 层图评分: HAS_QUALITY + HAS_PENALTY + ScoringRule + LEARNED_FOR."""
        active_features = [k for k, v in features.items() if v]
        if not active_features:
            return None

        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                result = session.run("""
                    MATCH (s:ArchitectureStyle)

                    // Layer 1: HAS_QUALITY 标签匹配 — 每匹配 tag +2
                    OPTIONAL MATCH (s)-[:HAS_QUALITY]->(q:QualityAttribute)
                    WHERE q.name IN $active_features
                    WITH s, count(DISTINCT q) * 2 AS tag_score,
                           collect(DISTINCT q.name) AS matched_attributes

                    // Layer 4: HAS_PENALTY 惩罚 — Feature→Style 负权重求和
                    OPTIONAL MATCH (feat:Feature)-[pen:HAS_PENALTY]->(s)
                    WHERE feat.name IN $active_features
                    WITH s, tag_score, matched_attributes,
                           coalesce(sum(pen.weight), 0) AS penalty_score

                    // Layer 3: ScoringRule 特定规则 — 条件全匹配才触发
                    OPTIONAL MATCH (rule:ScoringRule)-[:APPLIES_TO]->(s)
                    WHERE all(cond IN rule.required_features WHERE cond IN $active_features)
                    WITH s, tag_score, matched_attributes, penalty_score,
                           coalesce(sum(rule.bonus), 0) AS rule_bonus

                    // Layer 2: LEARNED_FOR 学习权重
                    OPTIONAL MATCH (s)-[lw:LEARNED_FOR]->(qf:QualityAttribute)
                    WHERE qf.name IN $active_features
                    WITH s, tag_score, matched_attributes, penalty_score, rule_bonus,
                           count(DISTINCT lw) AS learning_bonus

                    // 场景 + 风险 + 组合 (证据展示, 不参与评分)
                    OPTIONAL MATCH (s)-[:SUITABLE_FOR]->(sc:Scenario)
                    OPTIONAL MATCH (s)-[:HAS_RISK]->(r:Risk)
                    OPTIONAL MATCH (s)-[:COMPLEMENTS]->(c:ArchitectureStyle)
                    RETURN s.name AS style,
                           s.name_zh AS style_zh,
                           s.is_mainstream AS is_mainstream,
                           tag_score, penalty_score, rule_bonus, learning_bonus,
                           matched_attributes,
                           collect(DISTINCT sc.name) AS matched_scenarios,
                           collect(DISTINCT r.name) AS related_risks,
                           collect(DISTINCT c.name) AS combinable_styles
                    ORDER BY (tag_score + penalty_score + rule_bonus + learning_bonus) DESC
                """, {"active_features": active_features})

                scored = []
                for record in result:
                    graph_score = (record["tag_score"] + record["penalty_score"]
                                   + record["rule_bonus"] + record["learning_bonus"])
                    scored.append({
                        "style": record["style"],
                        "style_zh": record["style_zh"] or record["style"],
                        "graph_score": graph_score,
                        "tag_score": record["tag_score"],
                        "penalty_score": record["penalty_score"],
                        "rule_bonus": record["rule_bonus"],
                        "learning_bonus": record["learning_bonus"],
                        "is_mainstream": record.get("is_mainstream", False),
                        "matched_attributes": [a for a in record["matched_attributes"] if a],
                        "matched_scenarios": [s for s in record["matched_scenarios"] if s],
                        "related_risks": [r for r in record["related_risks"] if r],
                        "combinable_styles": [c for c in record["combinable_styles"] if c],
                    })

            driver.close()
            if not scored:
                return None
            return {"available": True, "active_features": active_features, "scored": scored}
        except Exception as e:
            logger.warning(f"Neo4j graph_score failed: {e}")
            return None

    @staticmethod
    def graph_risks(style_name: str) -> Optional[Dict[str, Any]]:
        """查询指定风格的 HAS_RISK 关系, 返回风险与建议."""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                result = session.run("""
                    MATCH (s:ArchitectureStyle {name: $style_name})-[:HAS_RISK]->(r:Risk)
                    RETURN r.name AS risk, r.suggestion AS suggestion
                """, {"style_name": style_name})
                risks = []
                suggestions = []
                for record in result:
                    if record["risk"]:
                        risks.append(record["risk"])
                    if record.get("suggestion"):
                        suggestions.append(record["suggestion"])
            driver.close()
            if not risks:
                return None
            return {"style": style_name, "main_risks": risks, "suggestions": suggestions}
        except Exception as e:
            logger.warning(f"Neo4j graph_risks failed: {e}")
            return None

    # ── 图状态 ──────────────────────────────────────────────────

    @staticmethod
    def graph_status() -> Dict[str, Any]:
        driver = _get_driver()
        if driver is None:
            return {"backend": "neo4j", "neo4j_available": False, "node_count": 0, "relationship_count": 0, "error": "Cannot connect to Neo4j"}
        try:
            with driver.session() as session:
                node_count = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
                rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]
            driver.close()
            return {"backend": "neo4j", "neo4j_available": True, "node_count": node_count, "relationship_count": rel_count, "uri": NEO4J_URI}
        except Exception as e:
            driver.close()
            return {"backend": "neo4j", "neo4j_available": False, "error": str(e)}

    # ── 架构组合 ────────────────────────────────────────────────

    @staticmethod
    def get_combinations() -> Optional[Dict[str, Any]]:
        """获取架构组合 (从 JSON, Neo4j 中也可查询 CONTAINS 关系)."""
        from .json_repository import JsonRepository
        return JsonRepository.get_combinations()

    # ── ADR 存储 (委托 JsonRepository, 可选 Neo4j 同步) ─────────

    @staticmethod
    def add_adr(adr_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存 ADR. JSON 为主存储, Neo4j 可用时同步创建 ADR 节点."""
        from .json_repository import JsonRepository
        result = JsonRepository.add_adr(adr_data)

        # Neo4j 同步: 创建 ADR 节点 + 与推荐风格/质量属性的关系
        try:
            driver = _get_driver()
            if driver is None:
                return result
            with driver.session() as session:
                session.run("""
                    CREATE (a:ADR {
                        adr_id: $adr_id,
                        timestamp: $ts,
                        requirement: $req,
                        recommended_style: $style
                    })
                """, {
                    "adr_id": result["adr_id"],
                    "ts": adr_data.get("timestamp", ""),
                    "req": adr_data.get("requirement", ""),
                    "style": adr_data.get("recommended_style", ""),
                })
                # 关联到 ArchitectureStyle 节点
                style_name = adr_data.get("recommended_style", "")
                if style_name:
                    session.run("""
                        MATCH (a:ADR {adr_id: $adr_id})
                        MATCH (s:ArchitectureStyle {name: $style})
                        MERGE (a)-[:RECOMMENDS]->(s)
                    """, {"adr_id": result["adr_id"], "style": style_name})
                # 关联到 QualityAttribute 节点
                features = adr_data.get("extracted_features", {})
                for feat, active in features.items():
                    if active:
                        session.run("""
                            MATCH (a:ADR {adr_id: $adr_id})
                            MERGE (q:QualityAttribute {name: $feat})
                            MERGE (a)-[:BASED_ON]->(q)
                        """, {"adr_id": result["adr_id"], "feat": feat})
            driver.close()
            logger.info(f"ADR synced to Neo4j: {result['adr_id']}")
        except Exception as e:
            logger.warning(f"ADR Neo4j sync failed (non-fatal): {e}")
        return result

    @staticmethod
    def get_adrs(limit: int = 20) -> Optional[Dict[str, Any]]:
        from .json_repository import JsonRepository
        return JsonRepository.get_adrs(limit)

    @staticmethod
    def get_adr(adr_id: str) -> Optional[Dict[str, Any]]:
        from .json_repository import JsonRepository
        return JsonRepository.get_adr(adr_id)
