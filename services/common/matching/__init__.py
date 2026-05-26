"""common.matching — 从 matching-agent 提取的共享纯函数模块。

api-gateway (subgraph) 和 matching-agent (HTTP endpoint) 共用这些函数,
保证评分逻辑的一致性。
"""

from .rules import score_style, select_top3, MAINSTREAM_STYLES
from .combo import score_combination, rank_combinations

__all__ = [
    "score_style",
    "select_top3",
    "MAINSTREAM_STYLES",
    "score_combination",
    "rank_combinations",
]
