# L07 · Evaluation Agent 评估与报告生成

> "评分是手段，解释是目的。好的推荐不仅要'对'，还要'让人觉得对'。"

---

## 本节目标

学完本节，你将能够：

1. 解释混合推理的三步流程：排序 → 投票 → 摘要
2. 说明 LLM 投票和摘要为什么用 `asyncio.gather` 并行执行
3. 理解降级摘要 `_fallback_summary()` 能做到什么程度
4. 说出 STYLE_RISK_MAP 覆盖了哪 3 种风格

---

## 为什么需要这个模块

### 从"候选列表"到"决策报告"

matching-agent 输出了一个候选列表：

```
Event-Driven Architecture: 7 分
Microservices:              6 分
Layered Architecture:       5 分
```

但用户不能只看分数。用户需要知道：
- **为什么是这个分**？——每条推荐的理由
- **三个候选之间怎么比**？——对比矩阵
- **选了这个有什么风险**？——风险与建议
- **最终结论是什么**？——核心推荐 + 备选

evaluation-agent 就是做这件事的——把一堆分数变成一份可读的决策报告。

---

## 当前项目如何实现

### 三步混合推理

```
输入: requirement + features + candidates
              │
    ┌─────────┴──────────┐
    │ Step 1: 规则排序    │  ← 始终执行
    │ 按 score 降序排列   │
    │ rule_best = ranked[0]
    └─────────┬──────────┘
              │
    ┌─────────┴──────────────────────┐
    │ Step 2: 并行 LLM (asyncio.gather)│  ← 可选
    │                                │
    │  ┌───────────┐ ┌─────────────┐ │
    │  │ LLM 投票  │ │ LLM 摘要    │ │
    │  │ temp=0.0  │ │ temp=0.3    │ │
    │  │ tie-break │ │ 生成报告    │ │
    │  └─────┬─────┘ └──────┬──────┘ │
    │        │              │        │
    └────────┼──────────────┼────────┘
             │              │
    ┌────────┴──────┐  ┌───┴──────────┐
    │ 投票结果:      │  │ 摘要失败:     │
    │ +1 分给所选   │  │ _fallback_   │
    │ 风格           │  │ summary()    │
    └───────────────┘  └──────────────┘
             │              │
    ┌────────┴──────────────┴──────────┐
    │ Step 3: 最终排序 + 对比矩阵 + 风险  │
    │ 重新按分排序，生成完整报告           │
    └──────────────────────────────────┘
```

### 为什么投票和摘要并行

```python
# evaluation_agent/app/main.py:279-284
llm_vote, llm_note = await asyncio.gather(
    llm_vote_style(payload.requirement, ranked),   # 两个 LLM 调用
    llm_summary(payload.requirement, ranked, rule_best_style),  # 互不依赖
)
```

这两个 LLM 调用**互不依赖**——投票不需要摘要的内容，摘要也不需要投票的结果。所以用 `asyncio.gather` 并行调用，总耗时约等于其中较慢的那个，而不是两者之和。

**这是一个面试亮点**：体现出对异步编程的理解和对 LLM 调用延迟的优化意识。

### LLM 投票：temperature=0.0

```python
# evaluation_agent/app/main.py:141-181
async def llm_vote_style(requirement, candidates):
    prompt = (
        "Select one best architecture style from given candidates. "
        "Return only the exact style name, no extra words.\n"
        f"Requirement: {requirement}\n"
        f"Candidates: {style_names}\n"
    )
    body = {"model": LLM_MODEL, "messages": [...], "temperature": 0.0}
    # ...
    if text in style_names:
        return text  # 只有精确匹配列表中的风格名才接受
    return None  # LLM 输出了不在列表中的名字 → 忽略
```

**两个设计要点**：
- **temperature=0.0**：这不是创意生成任务，这是"选一个"。需要确定性。
- **精确匹配校验**：`if text in style_names`——即使 LLM 输出 `"Event-Driven Architecture (recommended)"` ，也会被拒绝。防止 LLM 的自由发挥干扰排序。

### LLM 摘要：temperature=0.3 + Few-shot

```python
# evaluation_agent/app/main.py:59-111
async def llm_summary(requirement, candidates, best_style):
    # 尝试用 Few-shot prompt
    try:
        from common.prompts.evaluation_few_shot import build_few_shot_prompt
        prompt = build_few_shot_prompt(requirement, best_style, alt_styles, candidates_json)
    except ImportError:
        prompt = zero_shot_prompt(...)

    body = {"model": LLM_MODEL, "messages": [...], "temperature": 0.3}
```

temperature=0.3 比投票稍高——摘要需要一定的语言多样性（不同需求的表述不能千篇一律），但又不能太放飞。

### 降级摘要：规则也能生成报告

当 LLM 不可用时，`_fallback_summary()` 生成一份结构化中文报告：

```python
# evaluation_agent/app/main.py:114-138
def _fallback_summary(best_style, candidates):
    lines = [
        f"1. 推荐架构：{best_style}（核心推荐）",
        f"   备选架构：{'、'.join(alt)}",
        "",
        "2. 推荐理由：",
    ]
    for r in zh_reasons[:3]:
        lines.append(f"   - {r}")
    lines.append("")
    lines.append("3. 优缺点分析：")
    lines.append(f"   √ 优点：{'、'.join(best_pros)}")
    lines.append(f"   × 缺点：{'、'.join(best_cons)}")
    return "\n".join(lines)
```

**效果**：没有 LLM 也能拿到一份可读的四段式报告（推荐→理由→优劣→风险）。虽然不如 LLM 生成的生动，但结构完整、信息准确。

### 风险分析：3 种风格专属模板

```python
# evaluation_agent/app/main.py:212-248
STYLE_RISK_MAP = {
    "Event-Driven Architecture": {
        "main_risks": ["事件溯源实现复杂度高，调试困难", "事件一致性设计难度大...", "分布式链路追踪成本高"],
        "suggestions": ["引入消息队列+死信队列", "建立事件Schema版本管理", "部署分布式追踪系统"],
    },
    "Microservices": {
        "main_risks": ["分布式系统复杂度高", "服务间通信延迟", "运维成本高"],
        "suggestions": ["采用Saga模式", "引入服务网格", "建立统一API网关"],
    },
    "Layered Architecture": {
        "main_risks": ["跨层调用性能开销", "层级耦合影响面大", "横向扩展有限"],
        "suggestions": ["严格单向依赖", "CQRS读写分离", "水平扩展+负载均衡"],
    },
}
```

三种最常推荐的风格有专属风险模板，其他风格走通用模板。模板中每条风险都对应一条缓解建议。

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [evaluation_agent/app/main.py:271-392](../services/evaluation_agent/app/main.py#L271-L392) | `evaluate()` 端点 |
| [evaluation_agent/app/main.py:279-284](../services/evaluation_agent/app/main.py#L279-L284) | LLM 投票+摘要并行调用 |
| [evaluation_agent/app/main.py:141-181](../services/evaluation_agent/app/main.py#L141-L181) | `llm_vote_style()` 投票 |
| [evaluation_agent/app/main.py:59-111](../services/evaluation_agent/app/main.py#L59-L111) | `llm_summary()` 摘要 |
| [evaluation_agent/app/main.py:114-138](../services/evaluation_agent/app/main.py#L114-L138) | `_fallback_summary()` 降级 |
| [evaluation_agent/app/main.py:212-248](../services/evaluation_agent/app/main.py#L212-L248) | STYLE_RISK_MAP 风险模板 |
| [evaluation_agent/app/main.py:296-311](../services/evaluation_agent/app/main.py#L296-L311) | `comparison_matrix` 生成 |

---

## 面试官可能怎么问

**Q1: 为什么要 LLM 投票？规则引擎不是已经排好序了吗？**

> 规则引擎的排序是基于硬编码规则的，它依赖的是"特征命中"和"专家规则"。LLM 投票提供了另一种视角——语义理解。比如一个需求的表述比较特殊，规则引擎可能没有覆盖到某些细微信号，LLM 可以捕捉到。
>
> 但 LLM 投票的权重很低——只加 1 分（在总分一般是 5-10 分的体系中）。这意味着它只能做 tie-break（打平的时候区分谁更好），不能推翻规则引擎的结论。

**Q2: 为什么要并行调用投票和摘要？**

> 因为它们互不依赖。投票只需要候选列表和需求文本，摘要也一样。如果用串行调用，总延迟 = 投票延迟 + 摘要延迟（约 30-40 秒）。用 `asyncio.gather` 并行，总延迟 = max(投票延迟, 摘要延迟)（约 20 秒）。这在用户体验上是显著的差异。

**Q3: 如果 LLM 全部不可用，报告长什么样？**

> 报告仍然完整——有推荐风格、备选方案、规则理由、优缺点分析、风险分析、对比矩阵。只是 `llm_summary` 字段换成规则模板生成的结构化中文，`llm_vote` 字段为 null。从用户角度看，核心信息一样，只是表述更"模板化"而非"自然化"。

---

## 简历上如何表达

> 实现混合推理评估引擎：规则排序主导 + LLM 投票（temperature=0.0，tie-break）+ LLM 摘要（temperature=0.3，并行 asyncio.gather）；3 种核心风格专属风险模板 + 通用 fallback；LLM 不可用时降级摘要保证报告完整性。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| 三步推理 | 排序 → 并行（投票+摘要）→ 矩阵+风险 |
| asyncio.gather | 两个 LLM 调用互不依赖，并行减少延迟 |
| LLM 投票权重 | +1 分，只能 tie-break 不能推翻规则 |
| 降级摘要 | `_fallback_summary()` 用规则理由拼四段式中文报告 |
| 风险模板 | 3 种核心风格专属 + 1 种通用 |
| Temperature | 投票 0.0（确定），摘要 0.3（多样） |
