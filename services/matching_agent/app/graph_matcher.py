"""图谱关系匹配器 — 调用 knowledge-base 的 Neo4j 图谱接口获取关系证据.

【模块功能】
对 matching-agent 的规则评分结果做二次增强 — 从 Neo4j 知识图谱中
拉取质量属性匹配、场景关联、风险信息、可组合风格等结构化证据,
按 50% 上限融合到规则评分中。

【为什么图谱加分有 50% 上限】
防止 Neo4j 图谱证据过度影响推荐结果.
规则引擎是确定性评分, 图谱是辅助推理, LLM 是语义理解.
三层驱动模式中, 规则引擎是"主" (保证底线), 图谱和 LLM 是"辅" (提升上限).

【Neo4j 不可用时的降级】
fetch_graph_evidence() 返回 None → blend_scores() 保持原评分,
仅填充空图字段 (graph_score=0, matched_attributes=[] 等).
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from common.matching import blend_scores  # 共享纯函数

logger = logging.getLogger("matching-agent.graph")


async def fetch_graph_evidence(
    knowledge_base_url: str,
    features: Dict[str, bool],
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """调用 knowledge-base POST /graph/match 获取图谱匹配证据.

    knowledge-base 内部执行 Cypher:
      MATCH (q:QualityAttribute {name: $feat})
      MATCH (s:ArchitectureStyle)-[:HAS_QUALITY]->(q)
      OPTIONAL MATCH (s)-[:SUITABLE_FOR]->(sc:Scenario)
      OPTIONAL MATCH (s)-[:HAS_RISK]->(r:Risk)
      OPTIONAL MATCH (s)-[:COMPLEMENTS]->(c:ArchitectureStyle)
      RETURN ...

    Returns:
        None  — 图谱不可用 (Neo4j 未启动/连接失败), 调用者回退规则引擎
        dict  — {"available": True, "ranked": [...], "active_features": [...]}
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.post(
                f"{knowledge_base_url}/graph/match",
                json={"features": features},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("available"):
                logger.info("Graph match not available: %s", data.get("reason", "unknown"))
                return None
            logger.info(
                "Graph match returned %d styles for %d active features",
                len(data.get("ranked", [])),
                len(data.get("active_features", [])),
            )
            return data
    except Exception as e:
        logger.warning("Graph match request failed: %s", e)
        return None
