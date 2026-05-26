"""图谱关系匹配器 — 已废弃 (双驱动架构).

原用于调用 knowledge-base 的 Neo4j 图谱接口获取关系证据,
现已被 matching_subgraph.py 中的 graph_score_node 替代,
该节点直接通过 POST /graph/score 获取完整的图谱评分。
"""

# 保留此文件以维持向后兼容的 import, 但不再包含功能性代码.
