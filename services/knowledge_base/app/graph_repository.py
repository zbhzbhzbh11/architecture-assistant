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
                     user_choice: Optional[str], comment: Optional[str],
                     features: Optional[Dict[str, bool]] = None) -> Optional[Dict[str, Any]]:
        """保存反馈: Neo4j 为主存储, JSON 为冷备.
        features: LLM 已提取的 12 维特征 (优先使用, 避免关键词重新提取).
        Neo4j 不可用时返回 None 触发 _repo() fallback 到 JsonRepository."""
        # 1. Neo4j 存储 (主)
        try:
            total = GraphRepository._neo4j_save_feedback(
                requirement, recommended_style, user_choice, comment, features)
        except Exception as e:
            logger.warning(f"Neo4j feedback save failed, will fallback to JSON: {e}")
            return None

        # 2. JSON 冷备 (仅记录日志, 不重复计算权重 — Neo4j 已为权威源)
        try:
            from .json_repository import JsonRepository
            JsonRepository._save_feedback_log(
                requirement, recommended_style, user_choice, comment)
        except Exception as e:
            logger.warning(f"JSON feedback backup skipped: {e}")

        # 3. 从 Neo4j 重新计算权重 → 同步 LEARNED_FOR 关系 + JSON 缓存
        try:
            raw = GraphRepository._compute_weights_from_neo4j(features)
            normalized = _normalize_weights(raw)
            from .json_repository import _save_weights
            _save_weights(normalized)
            # 关键: 同步 LEARNED_FOR 关系到 Neo4j (避免边孤岛化)
            GraphRepository._sync_learned_for_edges(normalized)
            logger.info(f"Learned weights recomputed from Neo4j: {len(raw)} dims, normalized + LEARNED_FOR synced")
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
        """从 Neo4j HAS_FEATURE 关系直接计算学习权重 (图遍历).

        不再使用关键词提取 — 直接查 (f:Feedback)-[:HAS_FEATURE]->(q) 关系,
        保证与 _compute_weights_from_neo4j 使用相同的特征来源.
        """
        # 图遍历: Feedback → HAS_FEATURE → QualityAttribute
        rows = _run_query(
            "MATCH (f:Feedback)-[:HAS_FEATURE]->(q:QualityAttribute) "
            "RETURN q.name AS feature, f.recommended_style AS style, f.timestamp AS timestamp"
        )
        if rows is None:
            return None

        # 1. 聚合: 每条反馈加权衰减后累加到 raw 权重
        raw_weights: Dict[str, Dict[str, float]] = {}
        for row in (rows or []):
            feat = row.get("feature", "")
            style = row.get("style", "")
            ts = row.get("timestamp")
            if not feat or not style:
                continue
            decay = _decay_weight(ts)
            raw_weights.setdefault(feat, {}).setdefault(style, 0.0)
            raw_weights[feat][style] += decay

        # 2. 归一化
        normalized = _normalize_weights(raw_weights)

        # 3. 统计
        style_learn_counts: Dict[str, int] = {}
        for feat, style_map in raw_weights.items():
            for style_name, count in style_map.items():
                style_learn_counts[style_name] = style_learn_counts.get(style_name, 0) + int(count)

        return {
            "weights": normalized,
            "raw_weights": raw_weights,
            "total_feedback_learned": sum(style_learn_counts.values()),
            "style_learn_counts": style_learn_counts,
        }

    # ── Neo4j 内部辅助 ──────────────────────────────────────────

    @staticmethod
    def _neo4j_save_feedback(requirement: str, recommended_style: str,
                             user_choice: Optional[str], comment: Optional[str],
                             features: Optional[Dict[str, bool]] = None) -> int:
        """写入 Feedback 节点 + HAS_FEATURE 关系 (图谱原生建模).

        features 不作为数组属性存储, 而是创建:
          (f:Feedback)-[:HAS_FEATURE]->(q:QualityAttribute)
        这样权重计算可以用图遍历, 无需解析数组.
        """
        active_features = [k for k, v in (features or {}).items() if v]
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
                # 图关系: Feedback → QualityAttribute (替代数组属性)
                for feat in active_features:
                    session.run("""
                        MATCH (f:Feedback {requirement: $req, timestamp: $ts})
                        MERGE (q:QualityAttribute {name: $feat})
                        CREATE (f)-[:HAS_FEATURE]->(q)
                    """, {"req": requirement, "ts": datetime.now().isoformat(timespec="seconds"),
                          "feat": feat})
                total = session.run("MATCH (f:Feedback) RETURN count(f) AS cnt").single()["cnt"]
            driver.close()
            return total
        except Exception as e:
            logger.warning(f"Neo4j feedback save failed: {e}")
            raise

    @staticmethod
    def _compute_weights_from_neo4j(
            current_features: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Dict[str, float]]:
        """从 Neo4j 图遍历计算带衰减的 feature→style 权重.

        使用 (f:Feedback)-[:HAS_FEATURE]->(q:QualityAttribute) 关系,
        不再解析数组属性.
        """
        rows = _run_query(
            "MATCH (f:Feedback)-[:HAS_FEATURE]->(q:QualityAttribute) "
            "RETURN q.name AS feature, f.recommended_style AS style, f.timestamp AS timestamp"
        )
        if rows is None:
            return {}

        weights: Dict[str, Dict[str, float]] = {}
        for row in rows:
            feat = row.get("feature", "")
            style = row.get("style", "")
            ts = row.get("timestamp")
            if not feat or not style:
                continue
            decay = _decay_weight(ts)
            weights.setdefault(feat, {}).setdefault(style, 0.0)
            weights[feat][style] += decay
        # 合并当前反馈的 LLM 特征 (尚未写入 Neo4j)
        if current_features:
            active = [k for k, v in current_features.items() if v]
            target_style = None  # 由调用方上下文提供
            for feat in active:
                weights.setdefault(feat, {}).setdefault(target_style or "", 0.0)
                weights[feat][target_style or ""] += 1.0
        return weights

    @staticmethod
    def _sync_learned_for_edges(normalized: Dict[str, Dict[str, float]]) -> None:
        """将归一化权重同步到 Neo4j LEARNED_FOR 关系 (防止边孤岛化).

        每次 add_feedback 后调用, 确保图谱中的 LEARNED_FOR 连线
        反映最新的 Feedback 聚合结果, 而非停留在 init 时刻.
        """
        if not normalized:
            return
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                for feat, style_map in normalized.items():
                    for style_name, weight in style_map.items():
                        if weight > 0:
                            session.run("""
                                MATCH (s:ArchitectureStyle {name: $style})
                                MATCH (q:QualityAttribute {name: $feat})
                                MERGE (s)-[r:LEARNED_FOR]->(q)
                                SET r.weight = $weight
                            """, {"style": style_name, "feat": feat, "weight": weight})
            driver.close()
            logger.info(f"LEARNED_FOR edges synced: {sum(len(m) for m in normalized.values())} relationships")
        except Exception as e:
            logger.warning(f"LEARNED_FOR sync failed (non-fatal): {e}")

    @staticmethod
    def reset_learned_weights() -> Dict[str, Any]:
        """清空 Neo4j 中所有 Feedback 节点 + LEARNED_FOR 边, 并重置 JSON."""
        _run_query("MATCH (f:Feedback) DETACH DELETE f")
        _run_query("MATCH ()-[r:LEARNED_FOR]->() DELETE r")
        from .json_repository import _save_weights
        _save_weights({})
        logger.info("Learned weights reset: Feedback nodes + LEARNED_FOR edges + JSON cleared")
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

    # ── 图谱风险查询 ────────────────────────────────────────────

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

    @staticmethod
    def adr_stats() -> Optional[Dict[str, Any]]:
        """ADR 决策统计: 风格推荐频次 + 特征→风格关联 (Neo4j 多跳查询)."""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                # 风格推荐频次
                style_freq = session.run("""
                    MATCH (adr:ADR)-[:RECOMMENDS]->(s:ArchitectureStyle)
                    RETURN s.name AS style, s.name_zh AS style_zh, count(adr) AS cnt
                    ORDER BY cnt DESC
                """)
                style_stats = [{"style": r["style"], "style_zh": r.get("style_zh", r["style"]),
                                "count": r["cnt"]} for r in style_freq]

                # 特征→风格决策关联
                feat_style = session.run("""
                    MATCH (adr:ADR)-[:RECOMMENDS]->(s:ArchitectureStyle)
                    MATCH (adr)-[:BASED_ON]->(q:QualityAttribute)
                    RETURN q.name AS feature, s.name AS style, count(adr) AS cnt
                    ORDER BY cnt DESC
                """)
                feat_stats = [{"feature": r["feature"], "style": r["style"],
                               "count": r["cnt"]} for r in feat_style]

                # 总决策数
                total = session.run("MATCH (adr:ADR) RETURN count(adr) AS cnt").single()["cnt"]

            driver.close()
            return {"total_decisions": total, "style_stats": style_stats,
                    "feature_style_stats": feat_stats[:20]}
        except Exception as e:
            logger.warning(f"Neo4j adr_stats failed: {e}")
            return None
