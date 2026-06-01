"""Architecture Workflow State — LangGraph 编排的全局状态定义.

【作用】
定义 LangGraph StateGraph 的全局状态类型。
四个节点 (extract/match/evaluate/trace) 共享此 TypedDict,
节点通过返回值做 shallow merge 更新状态。

【TypedDict vs dataclass】
选择 TypedDict 是因为 LangGraph 原生的状态合并机制 (shallow merge)
与 dict 更新语义一致: state.update(node_return_value).
用普通 class 或 dataclass 需要自定义 merge 函数。

【字段生命周期】
  初始状态 (由 _langgraph_orchestrate 构造):
    requirement = 用户输入
    其他字段 = 空 dict/list

  extract_node 后更新:
    extracted_features, feature_hits

  match_node 后更新:
    candidates, combination_candidates

  evaluate_node 后更新:
    final_report

  trace_node 后更新:
    workflow_engine = "langgraph"

  errors 和 trace 各节点累加 (通过 state.setdefault)

【字段都是可选的 (total=False)】
这样初始状态可以只填充 requirement, 不需要把所有字段都写上.
"""

from typing import Any, Dict, List, TypedDict


class ArchitectureWorkflowState(TypedDict, total=False):
    """LangGraph 工作流的全局状态.

    所有字段均为可选 (total=False 继承自 TypedDict).
    """

    # ── 输入 ──
    # 由调用方 (_langgraph_orchestrate) 填充
    requirement: str

    # ── extract_node 产出 ──
    # features: 12 维 bool — {"high_concurrency": True, "real_time": True, ...}
    # feature_hits: 命中的关键词 — {"high_concurrency": ["万人","高并发"], ...}
    # llm_disputed: LLM 质疑的特征 — {"real_time": true} 表示 LLM 认为不应激活
    extracted_features: Dict[str, bool]
    feature_hits: Dict[str, List[str]]
    llm_disputed: Dict[str, bool]
    arch_inclination: Dict[str, Any]

    # ── match_node 产出 ──
    # candidates: 3 个按分排序的候选架构
    # combination_candidates: 组合推荐 (最多 3 个)
    candidates: List[Dict[str, Any]]
    combination_candidates: List[Dict[str, Any]]

    # ── evaluate_node 产出 ──
    # 完整报告: recommended_style, comparison_matrix, risk_and_suggestions, ...
    final_report: Dict[str, Any]

    # ── 容错与可观测 ──
    # errors: 各节点的异常消息列表 — ["extract: timeout", "match: 502"]
    # trace:  各节点的耗时记录 — [{"node":"extract","elapsed_ms":292,"status":"ok"}, ...]
    errors: List[str]
    trace: List[Dict[str, Any]]

    # ── 元数据 ──
    # "langgraph" 或 "manual" — trace_node 设置, 前端用此字段展示编排引擎类型
    workflow_engine: str
