"""Evaluation Agent — Few-shot Prompt 示例库.

覆盖 3 种典型推荐场景: Event-Driven, Microservices, Layered/CQRS.
每个示例展示完整的输出结构 (推荐架构 / 推荐理由 / 优缺点 / 风险与建议).
"""

from typing import Dict, List

# 3 个 few-shot 示例
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


def build_few_shot_prompt(requirement: str, best_style: str,
                          alt_styles: str, candidates_json: str) -> str:
    """构建含 few-shot 示例的摘要 prompt.

    在原有零样本 prompt 前加入 3 个参考示例,
    帮助 LLM 理解输出结构和专业术语风格.
    """
    shot_lines = ["以下是一些架构评审报告的参考示例，请注意输出的结构和专业表述：", ""]

    for i, ex in enumerate(EXAMPLES, 1):
        shot_lines.append(f"【参考示例 {i}】")
        shot_lines.append(f"需求：{ex['requirement']}")
        shot_lines.append(f"推荐：{ex['core_style']}（备选：{ex['alt_style']}）")
        shot_lines.append(f"报告：\n{ex['output']}")
        shot_lines.append("")

    few_shot_block = "\n".join(shot_lines)

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
