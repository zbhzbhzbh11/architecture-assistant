"""Architecture Workflow State — LangGraph 编排的状态定义.

每个节点读写此 TypedDict, 完成步骤后更新对应字段.
trace 列表记录每步的节点名称、耗时 ms 和状态, 用于可观测性.
"""

from typing import Any, Dict, List, Optional, TypedDict


class ArchitectureWorkflowState(TypedDict, total=False):
    """LangGraph workflow 的全局状态.

    所有字段均为可选, 初始状态仅需 requirement.
    各节点执行后逐步填充.
    """

    # ── 输入 ──
    requirement: str

    # ── 提取阶段 (extract_node) ──
    extracted_features: Dict[str, bool]
    feature_hits: Dict[str, List[str]]

    # ── 匹配阶段 (match_node) ──
    candidates: List[Dict[str, Any]]

    # ── 评估阶段 (evaluate_node) ──
    final_report: Dict[str, Any]

    # ── 错误与追踪 ──
    errors: List[str]
    trace: List[Dict[str, Any]]

    # ── 元数据 ──
    workflow_engine: str  # "langgraph" 或 "manual"
