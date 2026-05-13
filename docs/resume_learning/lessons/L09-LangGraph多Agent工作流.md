# L09 · LangGraph 多 Agent 工作流

> "LangGraph 给你的是一个正式的状态图——你可以跟任何人说：'看，这就是我的系统在干什么。'"

---

## 本节目标

学完本节，你将能够：

1. 解释 LangGraph StateGraph 的节点、边、状态定义三要素
2. 理解为什么本项目的图是"线性 DAG"而非更复杂的图
3. 说明 `build_workflow()` 的异常处理策略
4. 回答："LangGraph 和手动编排的区别是什么？"

---

## 为什么需要 LangGraph

### 从"面条代码"到"状态图"

如果你只有 3 个步骤（extract → match → evaluate），手写串行调用很简单。但如果有 10 个步骤，其中某些可以并行、某些有条件分支、某些需要人工审批呢？

手写的话你会写出这样的代码：

```python
if condition_a:
    result_1 = step_a()
    if result_1 > threshold:
        result_2 = step_b(result_1)
    else:
        result_2 = step_c(result_1)
else:
    result_2 = step_d()
result_3 = step_e(result_2)
```

这就是"面条代码"——逻辑散落在 if/else 中，改一步要通读所有分支。

LangGraph 的做法是：
```python
workflow = StateGraph(State)
workflow.add_node("a", node_a)
workflow.add_node("b", node_b)
workflow.add_node("c", node_c)
workflow.add_conditional_edges("a", router, {"path1": "b", "path2": "c"})
```

逻辑变成了显式的图结构——节点定义"做什么"，边定义"什么时候做"。把控制流从业务逻辑中分离出来。

---

## 当前项目如何实现

### 状态定义

```python
# api_gateway/app/workflow_state.py
class ArchitectureWorkflowState(TypedDict, total=False):
    # 输入
    requirement: str

    # extract_node 输出
    extracted_features: Dict[str, bool]
    feature_hits: Dict[str, List[str]]

    # match_node 输出
    candidates: List[Dict[str, Any]]

    # evaluate_node 输出
    final_report: Dict[str, Any]

    # 可观测性
    errors: List[str]
    trace: List[Dict[str, Any]]
```

**为什么用 TypedDict？** LangGraph 的 StateGraph 需要知道每一步会更新哪些字段。TypedDict 提供了类型安全——IDE 会有自动补全，字段拼写错误会被检查出来。

### 节点实现

每个节点是一个异步函数，接收当前状态，返回部分更新：

```python
# api_gateway/app/langchain_workflow.py:33-57
async def _extract_node(state: ArchitectureWorkflowState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{REQ_URL}/extract", json={"requirement": state["requirement"]})
            data = resp.json()
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append({"node": "extract", "elapsed_ms": elapsed, "status": "ok"})
        return {"extracted_features": data["features"], "feature_hits": data.get("feature_hits", {})}
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        state.setdefault("trace", []).append({"node": "extract", "elapsed_ms": elapsed, "status": "error"})
        state.setdefault("errors", []).append(f"extract: {e}")
        raise
```

**每个节点都做了两件事**：调用下游微服务 + 记录 trace。trace 是嵌入在状态中的——LangGraph 自动将返回值合并到全局状态，下一个节点可以读取上游节点的 trace。

### 图的构建

```python
# api_gateway/app/langchain_workflow.py:130-166
def build_workflow(req_url, match_url, eval_url):
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        logger.warning("langgraph not installed, falling back to manual")
        return None  # ← 返回 None 触发手动编排

    workflow = StateGraph(ArchitectureWorkflowState)

    workflow.add_node("extract", _extract_node)
    workflow.add_node("match", _match_node)
    workflow.add_node("evaluate", _evaluate_node)
    workflow.add_node("trace", _trace_node)

    workflow.add_edge(START, "extract")
    workflow.add_edge("extract", "match")
    workflow.add_edge("match", "evaluate")
    workflow.add_edge("evaluate", "trace")
    workflow.add_edge("trace", END)

    compiled = workflow.compile()
    return compiled
```

### 图的调用

```python
# api_gateway/app/main.py:144-163
async def _langgraph_orchestrate(payload):
    initial_state = {"requirement": payload.requirement, ...}
    result = await _langgraph_app.ainvoke(initial_state)
    return {
        "extracted_features": result.get("extracted_features", {}),
        ...
        "workflow_engine": "langgraph",
        "workflow_trace": result.get("trace", []),
    }
```

`ainvoke()` 是 LangGraph 的异步入口。传入初始状态（只填充 `requirement`），LangGraph 按图结构依次执行节点，最终返回完整的最终状态。

### 当前局限：为什么是线性 DAG

当前图只有 `add_edge`，没有 `add_conditional_edges`。这意味着所有请求走同一路径——提取 → 匹配 → 评估 → 追踪。

**诚实说**：在当前 3 步串行的场景下，LangGraph 和手动编排没有本质区别。引入 LangGraph 的动机是**框架就绪**——如果未来需要：
- 检测到重构需求时走不同路径
- 批量评估时 parallel fan-out
- 引入人工审批节点暂停流程

框架已经就绪，只需改图的边定义，不需要改节点实现。

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [api_gateway/app/langchain_workflow.py:130-166](../services/api_gateway/app/langchain_workflow.py#L130-L166) | `build_workflow()` 构建 |
| [api_gateway/app/langchain_workflow.py:33-57](../services/api_gateway/app/langchain_workflow.py#L33-L57) | `_extract_node()` 节点 |
| [api_gateway/app/langchain_workflow.py:60-81](../services/api_gateway/app/langchain_workflow.py#L60-L81) | `_match_node()` 节点 |
| [api_gateway/app/langchain_workflow.py:84-113](../services/api_gateway/app/langchain_workflow.py#L84-L113) | `_evaluate_node()`/`_trace_node()` 节点 |
| [api_gateway/app/workflow_state.py](../services/api_gateway/app/workflow_state.py) | TypedDict 状态 |
| [api_gateway/app/main.py:53-61](../services/api_gateway/app/main.py#L53-L61) | 启动选择引擎 |
| [api_gateway/app/main.py:144-163](../services/api_gateway/app/main.py#L144-L163) | `_langgraph_orchestrate()` 入口 |
| [api_gateway/app/main.py:88-140](../services/api_gateway/app/main.py#L88-L140) | `_manual_orchestrate()` fallback |

---

## 面试官可能怎么问

**Q1: LangGraph 在你的项目中是必需的吗？**

> 不是必需。系统设计为双引擎：LangGraph 可用时使用 StateGraph 编排；LangGraph 不可用时——无论是包没装还是运行时异常——自动回退到手写 httpx 编排。两种编排产出的报告完全一致。LangGraph 在本项目中的价值是**形式化建模**——把编排逻辑从业务代码中分离出来，让控制流可读、可维护、可扩展。

**Q2: 你的图为什么这么简单？就只有线性串行？**

> 当前主链路是确定性的三步流程——提取 → 匹配 → 评估。这三步有严格的先后依赖，没有条件分支的需要。所以图的拓扑结构就是最简单的线性 DAG。但 LangGraph 框架已经就绪——如果需要引入条件路由（如检测到重构需求走不同路径），只需将 `add_edge` 改为 `add_conditional_edges`，节点代码不需要改动。

**Q3: 你为什么不直接用 LangChain 的 Chain？**

> Chain 把步骤串成 `step1 | step2 | step3`，适合简单的流水线。但它的缺陷是不容易扩展——加条件分支、加并行、加人机交互都很 hacky。LangGraph 的 StateGraph 提供了更正式的控制流建模，虽然当前只是线性链，但它为更复杂的工作流预留了清晰的扩展路径。

---

## 简历上如何表达

> 使用 LangGraph StateGraph 建模 4 节点 Agent 工作流（extract→match→evaluate→trace），TypedDict 定义全局状态契约；LangGraph 不可用时自动回退手写 httpx 编排，确保零强依赖。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| LangGraph 的作用 | 把编排逻辑从业务代码中分离为显式的状态图 |
| 图的拓扑 | 当前为线性 DAG（串行），框架支持扩展为条件/并行 |
| 双引擎设计 | LangGraph 优先，ImportError 或运行时异常 → 手动 |
| 状态类型 | TypedDict，total=False，渐近填充 |
| 手动编排 | `_manual_orchestrate()` 约 50 行，功能完全等价 |
| 当前局限 | 无条件路由，串行场景下 LangGraph 优势不明显 |
