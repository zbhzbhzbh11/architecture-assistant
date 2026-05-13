# L04 · API Gateway 编排设计

> "编排是微服务的指挥棒——它不干活，但决定谁在什么时候干什么。"

---

## 本节目标

学完本节，你将能够：

1. 解释 API Gateway 的双引擎设计（LangGraph + 手动 fallback）
2. 理解 workflow_trace 的可观测性价值
3. 说出为什么 LangGraph 是可选的、System Prompt 是空的
4. 解释请求级缓存的设计决策

---

## 为什么需要编排层

### 一个"婚礼策划师"的类比

办婚礼需要：找场地、订酒店、请摄影师、安排化妆师、排座位...

你可以自己一个一个打电话（手动编排），也可以请一个婚礼策划师（编排引擎）。策划师不会帮你化妆也不会帮你拍照——但她知道：

1. **谁先谁后**：先定场地才能排座位
2. **谁依赖谁**：摄影师的安排取决于场地和时段
3. **出问题了怎么办**：摄影师堵车了，立刻调备选方案

API Gateway 就是这样一位"婚礼策划师"——它不提取特征、不匹配风格、不调用 LLM。但它知道这三个步骤的先后顺序，知道每个步骤的输入输出，也知道任何一步出问题时怎么办。

### 为什么不能"一个服务调所有"

如果每个 Agent 都直接调用其他 Agent：
- 依赖关系变成**网状**，牵一发而动全身
- 每个 Agent 都要知道其他 Agent 的地址和接口
- 追踪一个请求的完整路径极其困难

有了 Gateway：
- 依赖关系变成**星状**，Gateway 是唯一的Hub
- Agent 只暴露自己的接口，不关心谁调用它
- 一次请求的完整路径记录在 workflow_trace 中

---

## 当前项目如何实现

### 双引擎架构

这是本系统最精妙的设计之一——**启动时选择一个引擎，运行时这个引擎失败了还能切备用**。

```
启动时（main.py 第 53-61 行）:
  ┌──────────────────────────────────────┐
  │  try:                                │
  │      import langgraph                │
  │      _langgraph_app = build_workflow()│
  │      WORKFLOW_ENGINE = "langgraph"    │
  │  except ImportError:                 │
  │      _langgraph_app = None           │
  │      WORKFLOW_ENGINE = "manual"       │
  └──────────────────────────────────────┘

运行时（main.py 第 181-188 行）:
  ┌──────────────────────────────────────┐
  │  if _langgraph_app is not None:       │
  │      try:                            │
  │          result = _langgraph_orchestrate()│
  │      except Exception:               │
  │          result = _manual_orchestrate()│  ← LangGraph 挂了也切
  │  else:                               │
  │      result = _manual_orchestrate()   │
  └──────────────────────────────────────┘
```

**为什么这样设计？** 因为 LangGraph 是一个第三方 Python 包。在 Docker 环境中它可能安装成功，在本地开发环境可能没装。系统不应该因为一个可选依赖的缺失而无法启动。

### LangGraph 状态图

当 LangGraph 可用时，系统使用 StateGraph 建模工作流：

```
START
  │
  ▼
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ extract  │────▶│  match   │────▶│ evaluate │────▶│  trace   │────▶ END
│  _node   │     │  _node   │     │  _node   │     │  _node   │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
  │                 │                 │                │
  ▼                 ▼                 ▼                ▼
 调用 req-agent   调用 match-agent  调用 eval-agent   记录追踪
 /extract          /match            /evaluate
```

**状态定义**（[workflow_state.py](../services/api_gateway/app/workflow_state.py)）：

```python
class ArchitectureWorkflowState(TypedDict, total=False):
    requirement: str                    # 输入
    extracted_features: Dict[str, bool] # extract 输出
    candidates: List[Dict[str, Any]]    # match 输出
    final_report: Dict[str, Any]        # evaluate 输出
    errors: List[str]                   # 错误收集
    trace: List[Dict[str, Any]]         # 每步耗时 + 状态
```

**注意**：当前状态图是**线性 DAG**（串行），没有条件分支。这是有意为之——架构推荐的主链路是确定的：提取 → 匹配 → 评估。未来如果需要条件路由（如"检测到重构需求时走不同路径"），可以在 `add_edge` 处改为 `add_conditional_edges`。

### 手动编排（Manual Fallback）

当 LangGraph 不可用时，系统使用最朴素的 `httpx` 三步串行调用：

```python
async def _manual_orchestrate(payload):
    # Step 1: 调用 requirements-agent
    req_resp = await client.post(f"{REQ_URL}/extract", ...)
    extracted = req_resp.json()

    # Step 2: 调用 matching-agent
    match_resp = await client.post(f"{MATCH_URL}/match", ...)
    matching = match_resp.json()

    # Step 3: 调用 evaluation-agent
    eval_resp = await client.post(f"{EVAL_URL}/evaluate", ...)
    final_report = eval_resp.json()
```

三段代码功能等价——无论是 LangGraph 还是手动编排，用户拿到的报告完全一样。唯一区别是 `workflow_engine` 字段：`"langgraph"` 或 `"manual"`。

### 请求级缓存

在进入编排之前，先查缓存：

```python
# 缓存键 = SHA256(requirement + model + knowledge_version)[:16]
key = cache_key(payload.requirement, LLM_MODEL)
cached = cache_get(key)
if cached is not None:
    cached["cache_hit"] = True
    return cached  # 直接返回，跳过所有 Agent 调用

# ... 编排执行 ...

cache_set(key, result)  # 结果写回缓存
```

**缓存键设计的巧妙之处**：
- 包含 `requirement` → 相同需求返回相同结果
- 包含 `LLM_MODEL` → 换了模型（如从 deepseek 换成 qwen）缓存不共享
- 包含 `knowledge_version` → 知识库更新了（如新增了一种风格），旧缓存自动失效

`knowledge_version` 的默认值是 `architecture_styles.json` 文件的 MD5 前 8 位。这意味着：只要你改了知识库文件，所有旧缓存自动作废——不需要手动清。

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [api_gateway/app/main.py:53-61](../services/api_gateway/app/main.py#L53-L61) | 启动选择引擎 |
| [api_gateway/app/main.py:88-140](../services/api_gateway/app/main.py#L88-L140) | 手动编排 `_manual_orchestrate()` |
| [api_gateway/app/main.py:144-163](../services/api_gateway/app/main.py#L144-L163) | LangGraph 编排 `_langgraph_orchestrate()` |
| [api_gateway/app/main.py:166-220](../services/api_gateway/app/main.py#L166-L220) | `/recommend` 端点（含缓存+重构调用） |
| [api_gateway/app/langchain_workflow.py:130-166](../services/api_gateway/app/langchain_workflow.py#L130-L166) | `build_workflow()` 构建 |
| [api_gateway/app/workflow_state.py](../services/api_gateway/app/workflow_state.py) | TypedDict 状态定义 |
| [common/cache/hash_utils.py:29-36](../services/common/cache/hash_utils.py#L29-L36) | `cache_key()` 生成 |
| [common/cache/hash_utils.py:10-22](../services/common/cache/hash_utils.py#L10-L22) | `knowledge_version()` 计算 |

---

## 面试官可能怎么问

**Q1: 为什么用 LangGraph？它做了什么普通 .py 脚本做不到的事？**

> LangGraph 提供了状态图的形式化建模。第一，它把"先调谁、后调谁"的编排逻辑从业务代码中分离出来，可读性更强；第二，StateGraph 的 TypedDict 定义了每一步的输入输出契约，新增或调整步骤不容易出错；第三，它为未来扩展（条件路由、并行节点、人机交互）预留了框架。
>
> 但诚实地说——当前的线性链用普通 Python 也能实现，所以 LangGraph 在本项目中是**可选依赖**，不可用时自动回退到手写编排。这是一种务实的工程选择。

**Q2: 为什么你设计了双引擎？是不是过度设计？**

> 不是。这是对"第三方依赖不稳定"的防御。LangGraph 在 Docker 镜像中可能安装成功，但在同学的本地电脑上可能因为 pip 源问题装不上。如果系统因为一个可选依赖装不上就无法启动，那它在答辩时就无法演示。
>
> 双引擎设计的成本其实很低——手动编排只有 50 行代码（`_manual_orchestrate`），和 LangGraph 编排共享完全相同的 Agent 调用逻辑。维护成本几乎为零。

**Q3: workflow_trace 记录了什么？有什么用？**

> 每次请求的每一步——extract、match、evaluate——都记录了节点名称、耗时（毫秒）和状态（ok/error）。这有两个用途：第一是**调试**，如果某次推荐很慢，看 trace 就知道卡在哪一步；第二是**演示**，答辩时可以在前端追踪面板展示每一步的耗时，让评委看到系统的运行过程。

---

## 简历上如何表达

> 设计 API Gateway 的双引擎编排架构：优先使用 LangGraph StateGraph 建模 Agent 工作流，LangGraph 不可用时自动回退到手写 httpx 编排；实现 SHA256 请求级缓存，结合 knowledge_version 自动失效机制保证缓存一致性。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| Gateway 的角色 | 不是"干活的人"，是"指挥干活的人" |
| 双引擎 | LangGraph 优先，手动编排兜底 |
| fallback 层级 | 启动判断 + 运行捕获，双重保险 |
| 缓存键 | requirement + model + knowledge_version |
| 缓存自动失效 | knowledge_version 用 styles 文件 MD5，改了知识库就失效 |
| 当前限制 | 状态图是线性 DAG，未使用条件路由 |
