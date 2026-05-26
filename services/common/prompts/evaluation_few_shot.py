"""Evaluation Agent — Few-shot Prompt 示例库.

【模块功能】
为 evaluation-agent 的 LLM 摘要生成 (llm_summary) 提供 3-shot prompt。
帮助 LLM 生成结构一致、专业术语准确的架构评审报告。

【为什么需要 Few-shot】
- 零样本 LLM 输出的报告格式不稳定 (有时用"优点:"有时用"优势:")
- 3 个示例教会 LLM 固定输出格式:
  推荐架构 → 推荐理由 → 优缺点分析 → 风险与建议
- 示例覆盖三种主流风格, 让 LLM 学会不同场景的表述风格:
  示例1: 事件驱动 (IM系统, 高并发+实时+松耦合)
  示例2: 微服务 (电商, 多团队+强一致+独立部署)
  示例3: 分层架构 (企业审批, 稳定迭代+低复杂度)

【使用方式】evaluation_agent/app/main.py 第 70-73 行:
  try: prompt = build_few_shot_prompt(...)  → 3-shot
  except ImportError: prompt = 零样本版本    → fallback
"""

from typing import Dict, List

# 3 个 few-shot 示例 — 每个是完整的架构评审报告
# 结构: requirement (需求), core_style (核心推荐), alt_style (备选), output (报告全文)
# 统一按 "推荐架构→推荐理由→优缺点→风险建议" 四段式组织
EXAMPLES: List[Dict[str, str]] = [
    {
        "requirement": "开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话。",
        "core_style": "Event-Driven Architecture（事件驱动架构）",
        "alt_style": "Microservices（微服务架构）",
        "output": (
            "1. 推荐架构：\n"
            "   核心推荐：Event-Driven Architecture（事件驱动架构）\n"
            "   备选架构：Microservices（微服务架构）\n"
            "\n"
            "2. 推荐理由：\n"
            "   - 高并发万人同时在线的场景，事件异步处理天然适合削峰填谷，避免同步调用的雪崩效应。\n"
            "   - 松耦合的事件通道便于后续扩展视频通话模块，新增消费者不影响已有生产者。\n"
            "   - 消息队列的持久化机制保障了消息的可靠投递，满足实时性要求。\n"
            "\n"
            "3. 优缺点分析：\n"
            "   √ 优点：高吞吐量，模块间松耦合，扩展性强，天然支持异步解耦。\n"
            "   × 缺点：事件溯源实现复杂度高，链路追踪和调试困难，最终一致性设计需额外处理幂等与乱序。\n"
            "\n"
            "4. 风险与建议：\n"
            "   风险：事件一致性设计难度大，分布式链路追踪成本高。\n"
            "   建议：引入 Kafka/RabbitMQ + 死信队列，建立事件 Schema 版本管理，部署分布式追踪系统（Jaeger）。"
        ),
    },
    {
        "requirement": "构建电商平台，订单支付库存需要强一致事务，双十一高峰要抗压，多团队并行开发。",
        "core_style": "Microservices（微服务架构）",
        "alt_style": "Event-Driven Architecture（事件驱动架构）",
        "output": (
            "1. 推荐架构：\n"
            "   核心推荐：Microservices（微服务架构）\n"
            "   备选架构：Event-Driven Architecture（事件驱动架构）\n"
            "\n"
            "2. 推荐理由：\n"
            "   - 多团队并行开发订单、支付、库存模块，微服务独立部署的边界天然匹配组织架构。\n"
            "   - 双十一高并发场景下，各服务可独立横向扩容，提高资源利用率。\n"
            "   - 订单支付等核心链路对强一致性要求高，微服务内可采用 Saga 模式或两阶段提交保障事务。\n"
            "\n"
            "3. 优缺点分析：\n"
            "   √ 优点：高可扩展性，独立发布部署，技术栈灵活，团队自治。\n"
            "   × 缺点：分布式系统复杂度高，服务间通信延迟和网络故障风险增大，运维成本较高。\n"
            "\n"
            "4. 风险与建议：\n"
            "   风险：分布式事务一致性难保障，服务间网络故障可能导致级联失败。\n"
            "   建议：采用 Saga 模式处理分布式事务，引入服务网格（Istio）管理通信，建立统一 API 网关。"
        ),
    },
    {
        "requirement": "企业内部审批系统，流程复杂规则多，需要稳定迭代，对数据一致性要求高。",
        "core_style": "Layered Architecture（分层架构）",
        "alt_style": "Hexagonal Architecture（六边形架构）",
        "output": (
            "1. 推荐架构：\n"
            "   核心推荐：Layered Architecture（分层架构）\n"
            "   备选架构：Hexagonal Architecture（六边形架构）\n"
            "\n"
            "2. 推荐理由：\n"
            "   - 企业内部审批流程层次分明，表现层→应用层→领域层→基础设施层的分层模型与业务天然对齐。\n"
            "   - 复杂业务规则集中在领域层，便于维护和测试，支持稳定迭代。\n"
            "   - 强一致性需求在单体或少量服务内更容易保障，分层架构的简单性降低了事务管理复杂度。\n"
            "\n"
            "3. 优缺点分析：\n"
            "   √ 优点：可维护性高，职责边界清晰，团队学习成本低，适合长期稳定迭代。\n"
            "   × 缺点：跨层调用带来性能开销，高并发场景可能成为瓶颈，横向扩展能力有限。\n"
            "\n"
            "4. 风险与建议：\n"
            "   风险：层级耦合可能导致变更影响面大，横向扩展能力不足。\n"
            "   建议：严格遵循单向依赖，核心业务层可结合 CQRS 读写分离缓解性能压力。"
        ),
    },
]


def build_few_shot_prompt(
    requirement: str, best_style: str, alt_styles: str, candidates_json: str
) -> str:
    """构建含 3 个 few-shot 示例的架构评审 prompt.

    【算法】
    1. 遍历 EXAMPLES, 每条展示: 原需求 + 推荐风格 + 完整报告
    2. 在示例后追加当前用户的需求、推荐风格、候选详情
    3. 要求 LLM 参照示例的格式和风格输出

    【输出结构】
    四段式固定格式:
      1. 推荐架构 (核心推荐 + 备选)
      2. 推荐理由 (2-3条要点)
      3. 优缺点分析 (√ 优点, × 缺点)
      4. 风险与建议 (风险 + 建议)

    【为什么 3 个示例而不是 1 个或 6 个】
      1 个 → LLM 倾向复制示例中的具体内容而非推理
      6 个 → token 消耗大, 对于格式约束来说过度
      3 个 → 恰好覆盖三种主流风格 + 展示不同领域表述
    """
    shot_lines = ["以下是一些架构评审报告的参考示例，请注意输出的结构和专业表述：", ""]

    for i, ex in enumerate(EXAMPLES, 1):
        shot_lines.append(f"【参考示例 {i}】")
        shot_lines.append(f"需求：{ex['requirement']}")
        shot_lines.append(f"推荐：{ex['core_style']}（备选：{ex['alt_style']}）")
        shot_lines.append(f"报告：\n{ex['output']}")
        shot_lines.append("")

    few_shot_block = "\n".join(shot_lines)

    # 在实际需求前追加当前上下文, 要求按示例格式输出
    prompt = (
        f"{few_shot_block}\n"
        "---\n"
        "现在，请根据以下用户需求和候选架构，参照上述示例的风格和结构，用中文输出：\n\n"
        "1. 推荐架构：【核心推荐】和【备选架构】\n"
        "2. 推荐理由：（2-3条要点）\n"
        "3. 优缺点分析：\n"
        "   √ 优点：...\n"
        "   × 缺点：...\n"
        "4. 风险与建议：\n"
        "   风险：...\n"
        "   建议：...\n\n"
        f"用户需求：{requirement}\n"
        f"核心推荐：{best_style}\n"
        f"备选架构：{alt_styles if alt_styles else '无'}\n"
        f"候选详情：{candidates_json}\n"
    )
    return prompt
