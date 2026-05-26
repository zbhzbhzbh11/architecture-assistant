"""架构组合推荐器 — 异步数据获取层。

纯函数 (score_combination, rank_combinations) 已提取到
services/common/matching/combo.py 作为共享模块。

本文件保留异步 HTTP 数据获取逻辑:
  fetch_combinations() — 从 knowledge-base GET /combinations 拉取组合定义
"""

import logging
from typing import Any, Dict, List

import httpx

from common.matching import score_combination, rank_combinations

logger = logging.getLogger("matching-agent.combo")


async def fetch_combinations(knowledge_base_url: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """从 knowledge-base GET /combinations 拉取架构组合列表.

    数据源: services/knowledge_base/data/architecture_combinations.json (5 种组合).
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.get(f"{knowledge_base_url}/combinations")
            resp.raise_for_status()
            return resp.json().get("combinations", [])
    except Exception as e:
        logger.warning(f"Failed to fetch combinations: {e}")
        return []
