"""Requirements Agent — Few-shot Prompt 示例库.

覆盖 6 种典型场景: 模糊高并发、否定语义、安全合规、
数据密集、强一致、架构重构倾向.

每个示例: (需求文本, {特征名: true/false})
仅标注 true 的特征 (规则未命中时由 LLM 补充).
不覆盖已由规则引擎命中的特征.
"""

from typing import Dict, List, Tuple

# 10 个特征维度的中文标签 (与 FEATURE_LABELS_ZH 一致)
FEATURE_LABELS_ZH: Dict[str, str] = {
    "high_concurrency": "高并发",
    "real_time": "实时性",
    "reliability": "可靠性",
    "scalability": "可扩展性",
    "complex_business": "复杂业务",
    "strict_consistency": "强一致性",
    "deployment_constraint": "部署约束",
    "data_intensive": "数据密集型",
    "team_size_large": "多团队协作",
    "security": "安全性",
}

# 6 个 few-shot 示例
EXAMPLES: List[Tuple[str, Dict[str, bool]]] = [
    (
        "我们的系统预计日活百万，双十一期间流量会暴增，需要保证用户体验不降级。",
        {"high_concurrency": True, "scalability": True},
    ),
    (
        "后台管理系统，不需要实时处理。数据白天录入，晚上批量跑报表即可。",
        {"real_time": False},
    ),
    (
        "医疗数据平台，涉及患者隐私，需要脱敏、审计追踪和权限分级管理。",
        {"security": True},
    ),
    (
        "每天从上千台服务器采集 TB 级日志，经 ETL 管道清洗后写入数据仓库供分析。",
        {"data_intensive": True},
    ),
    (
        "银行核心转账系统，每笔交易必须 ACID 一致提交，不允许部分成功。",
        {"strict_consistency": True, "reliability": True},
    ),
    (
        "现有单体电商系统性能瓶颈严重，计划按订单、支付、库存拆分为独立服务，"
        "多个团队并行开发各自模块，需要支持独立发布部署。",
        {"team_size_large": True, "scalability": True},
    ),
]


def build_few_shot_prompt(user_requirement: str) -> str:
    """构建含 few-shot 示例的语义补全 prompt.

    输出约束严格: 只返回 JSON, 不输出其他内容.
    """
    zh_labels = ", ".join(FEATURE_LABELS_ZH.values())

    # 构建 few-shot 部分
    shot_lines = ["以下是一些需求分析的示例，请参考它们的判断方式：", ""]
    for i, (text, labels) in enumerate(EXAMPLES, 1):
        # 构建全维度 JSON (未标注的默认为 false)
        full_json = {zh: labels.get(eng, False) for eng, zh in FEATURE_LABELS_ZH.items()}
        import json as _json
        shot_lines.append(f"示例{i}:")
        shot_lines.append(f"  需求: {text}")
        shot_lines.append(f"  输出: {_json.dumps(full_json, ensure_ascii=False)}")
        shot_lines.append("")

    few_shot_block = "\n".join(shot_lines)

    prompt = (
        f"{few_shot_block}\n"
        "---\n"
        "请分析以下软件需求描述, 判断是否涉及这些特征维度: "
        f"{zh_labels}。\n"
        "返回严格的 JSON 格式: {\"特征名\": true/false}, 不要输出其他内容。\n"
        "\n"
        f"需求: {user_requirement}"
    )
    return prompt
