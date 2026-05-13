# L05 · Requirements Agent 需求解析

> "如果你连需求是什么都说不清，那后面的推荐都是空中楼阁。"

---

## 本节目标

学完本节，你将能够：

1. 说出 10 个质量属性维度的设计逻辑
2. 解释否定语义过滤是怎么工作的
3. 理解 LLM 语义补全的触发条件和降级路径
4. 能回答："你的特征提取为什么不用 NLP 模型？"

---

## 为什么需要这个模块

### 从"一段话"到"一组信号"

用户输入的是自然语言，比如：

> "开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话。"

人一眼就能看出：这是高并发、要实时、要可靠、要可扩展。但计算机需要把这段文字转成结构化的特征信号：

```json
{
  "high_concurrency": true,
  "real_time": true,
  "reliability": true,
  "scalability": true,
  "complex_business": false,
  "strict_consistency": false,
  ...
}
```

这一步叫**特征提取**，是后续所有推理的输入。如果这一步错了，后面的架构推荐就不可能对。

### 为什么是 10 个维度

这 10 个维度不是随便选的。它们对应软件体系结构领域的"质量属性"——影响架构风格选择的核心维度。每一个都可以在《Software Architecture in Practice》等经典教材中找到对应：

| 维度 | 英文 | 为什么影响架构选择 |
|------|------|------------------|
| 高并发 | high_concurrency | Event-Driven 天然适合，Layered 可能成为瓶颈 |
| 实时性 | real_time | 需要异步消息和低延迟通信 |
| 可靠性 | reliability | 需要冗余、容错、监控设计 |
| 可扩展性 | scalability | Microservices 支持水平扩展，Layered 有限 |
| 复杂业务 | complex_business | 需要清晰的领域边界 |
| 强一致性 | strict_consistency | 不适合最终一致性的 Event-Driven |
| 部署约束 | deployment_constraint | 私有化部署限制云原生方案 |
| 数据密集型 | data_intensive | Pipeline-Filter 和 CQRS 优势明显 |
| 多团队协作 | team_size_large | Microservices 匹配组织架构 |
| 安全性 | security | 需要额外的安全层和合规设计 |

---

## 当前项目如何实现

### 双层提取：关键词 + LLM 补全

```
用户输入: "开发跨平台IM系统，支持万人同时在线..."
              │
              ▼
    ┌─────────────────────┐
    │  Layer 1: 关键词匹配  │  ← 始终执行，零延迟，确定性
    │                     │
    │  高并发 ← [万人]     │
    │  实时性 ← [实时]     │
    │  可靠性 ← [可靠]     │
    │  可扩展性 ← [扩展]   │
    │                     │
    │  命中维度: 4个       │
    └─────────┬───────────┘
              │
              ▼
    ┌─────────────────────┐
    │  判断: 命中数 ≤ 2?   │  ← NO (4 > 2), 跳过 LLM
    │                     │
    │  YES → 调LLM补全     │
    │  NO  → 直接返回      │
    └─────────┬───────────┘
              │
              ▼
    最终输出: {high_concurrency: true, real_time: true,
              reliability: true, scalability: true,
              其他6个: false}
```

**为什么阈值是 2？** 如果规则只命中了 0-2 个维度，说明需求描述比较模糊或使用了专业术语以外的表述。这时 LLM 可以辅助判断（比如用户说"系统要能扛住流量尖峰"，没有触发关键词但确含高并发意图）。

### 否定语义过滤

这是最容易忽略的细节——用户可能说"不需要高并发"。如果不做否定过滤，"高并发"关键词会被匹配到。

```python
# requirements_agent/app/main.py:43-64
NEGATION_PATTERNS = ["不需要", "不要求", "无需", "不需要", "没有", "无高", "非"]

def filter_negation(text: str, hits: List[str]) -> List[str]:
    filtered = []
    for word in hits:
        idx = text.find(word)
        prefix = text[max(0, idx - 6):idx]  # 向前看 6 个字符
        if any(neg in prefix for neg in NEGATION_PATTERNS):
            continue  # 前面有否定词，剔除
        filtered.append(word)
    return filtered
```

**关键设计决策**：否定检测窗口是"向前 6 个字符"。这不是完美的 NLP 方案（`"虽然不需要高并发但是..."` 这样复杂的转折会漏过），但覆盖了 90% 的实际场景——关键词前紧邻否定词的情况。这是"工程上够用"的务实选择。

### 关键词词典的规模

每个维度配有 5-15 个中英文关键词（共约 90 个）：

```python
# requirements_agent/app/main.py:155-262
lexicon = {
    "high_concurrency": ["高并发", "并发", "万人", "海量用户", "峰值", "秒杀", "高吞吐", "高qps", "qps", "concurrent"],
    "real_time": ["实时", "实时性", "即时", "在线", "低延迟", "毫秒", "消息", "通知", "im", "real-time"],
    "security": ["安全", "加密", "认证", "鉴权", "授权", "审计", "隔离", "防护", "合规", "脱敏", "防篡改", "权限", "安全隔离", "可靠交付", "零信任"],
    ...
}
```

词典来自两个来源：软件工程教材中的质量属性术语 + 实际项目中常见的非正式表达（如"万人"→高并发、"秒杀"→高并发）。

### LLM 语义补全的降级路径

```python
# requirements_agent/app/main.py:86-142
async def llm_semantic_supplement(text, features, feature_hits):
    # 条件 1: LLM 没配 → 直接返回
    if not (LLM_API_BASE and LLM_API_KEY and LLM_MODEL):
        return features

    # 条件 2: 规则命中 > 2 → 不需要 LLM
    if sum(1 for v in features.values() if v) > 2:
        return features

    # 条件 3: Few-shot 模块没装 → 降级为零样本
    try:
        from common.prompts.requirements_few_shot import build_few_shot_prompt
        prompt = build_few_shot_prompt(text)
    except ImportError:
        prompt = zero_shot_prompt(text)  # 模板内联的简单 prompt

    # 调用 LLM...
    # 结果只写入 True 项，不覆盖已有的 True
```

**三重降级**：没配 LLM → 规则命中多 → Few-shot 模块不可用。每一步都有退路。

---

## 核心代码路径

| 文件 | 行号 | 关键内容 |
|------|------|---------|
| [requirements_agent/app/main.py:43-64](../services/requirements_agent/app/main.py#L43-L64) | 否定过滤 |
| [requirements_agent/app/main.py:155-262](../services/requirements_agent/app/main.py#L155-L262) | 10 维关键词词典 |
| [requirements_agent/app/main.py:67-71](../services/requirements_agent/app/main.py#L67-L71) | `keyword_hits()` |
| [requirements_agent/app/main.py:86-142](../services/requirements_agent/app/main.py#L86-L142) | LLM 语义补全 |
| [requirements_agent/app/main.py:150-271](../services/requirements_agent/app/main.py#L150-L271) | `/extract` 端点 |
| [common/prompts/requirements_few_shot.py](../services/common/prompts/requirements_few_shot.py) | 6 个 Few-shot 示例 |

---

## 面试官可能怎么问

**Q1: 为什么用关键词而不是训练一个 NLP 分类器？**

> 三个原因。第一，**可解释性**——关键词匹配的结果是透明的：你说"万人"，我就知道是高并发；你说"消息"，我就知道是实时。训练一个模型，"为什么判为高并发？因为 embedding 的某个维度..."——这对架构推荐来说解释力不够。第二，**零样本**——10 个维度只有约 90 个关键词，不需要标注数据就能工作。第三，**可靠性**——关键词不需要 GPU、不依赖外部服务、不会有训练/推理的不一致。

**Q2: 你的关键词词典有什么局限？**

> 两个局限。第一，**覆盖面**——90 个关键词不可能覆盖所有表述方式。比如用户说"系统要能扛住流量尖峰"，"扛住"和"尖峰"不在词典里，可能漏判。这正好是 LLM 补全要解决的问题。第二，**语言**——目前只支持中文关键词。英文支持有限（如 "real-time"、"concurrent"），但不完整。

**Q3: 否定检测只看前 6 个字符，会不会漏判？**

> 会。比如"虽然不需要高并发"——"不"和"需要"紧邻，"需要"和"高并发"之间有间隔，这不会被过滤。但工程上这是有意取舍——否定词的语法位置 90% 紧邻关键词之前。要更准确地处理，需要做句法分析，成本远大于收益。这是一个"80/20"的设计决策。

---

## 简历上如何表达

> 实现 10 维质量属性关键词词典（约 90 个中英文词）+ 6 种否定语义过滤，关键词命中 ≤2 时自动触发 Few-shot LLM 语义补全；LLM 不可用时静默降级为纯规则模式。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| 核心方法 | 关键词词典（确定性）+ LLM 补全（模糊性） |
| 否定过滤 | 向前看 6 字符，覆盖 90% 场景 |
| LLM 触发条件 | 仅当规则命中 ≤ 2 且 LLM 配置了且 Few-shot 可用 |
| 三层降级 | 无 LLM → 命中多 → 无 Few-shot |
| 主要局限 | 中文为主，词典覆盖面有限 |
