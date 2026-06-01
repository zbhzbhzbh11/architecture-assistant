
"""Requirements Agent — Few-shot Prompt 示例库.

【模块功能】
为 requirements-agent 的 LLM 独立分析 (llm_analyze) 提供 12-shot prompt。
LLM 是特征提取的主路径 — 独立理解需求语义，不受规则引擎影响。
当规则引擎命中维度 <= 2（特征稀疏）时触发，帮助 LLM 识别词典覆盖不到的隐含特征。

【为什么需要 Few-shot】
- 关键词词典无法覆盖"日活百万"→高并发、"毫秒级"→实时性 这种非标准表述
- Few-shot 示例教会 LLM 从模糊描述中推断特征，弥补词典盲区
- 示例2 专门教 LLM 识别"不需要""无需"等否定模式，防止误报

【设计原则】
- 12 个示例覆盖全部 12 个维度，每个维度至少 1 个正面示例
- 场景多样性: 电商/银行/医疗/大数据/企业ERP/军工/股票/报表
- 示例7 降低 data_intensive 阈值: "百万条记录" 也是数据密集型
- 示例8 教 LLM 识别实时性正面场景: "毫秒级推送"
- 示例9 教 LLM 识别复杂业务流程: "多个业务模块/审批流程/数据依赖"
- 示例10 教 LLM 识别部署约束: "内网/本地服务器/不能连外网"
- 只标注 True 的特征 (未标注默认=False), 减少 LLM 输出 token
- prompt 末尾强制 JSON 输出, temperature=0.1 保证稳定输出

【使用方式】requirements_agent/app/main.py:
  try: prompt = build_few_shot_prompt(text)  → 12-shot
  except ImportError: prompt = 零样本版本     → fallback
"""

from typing import Dict, List, Tuple

# 12 个特征维度的中文标签
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
    "simple_crud": "极简业务",
    "resource_constrained": "资源受限",
}

# 12 个 few-shot 示例 — 覆盖全部 12 个维度
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
    (
        "运营数据分析平台，每天从多个业务系统同步几百万条记录，"
        "需要生成日报、周报和多维分析报表，数据量持续增长。",
        {"data_intensive": True, "scalability": True},
    ),
    (
        "股票行情推送系统，价格变动需要在毫秒级同步到所有客户端，"
        "延迟超过100ms就会影响交易决策，对实时性要求极高。",
        {"real_time": True, "reliability": True},
    ),
    (
        "企业ERP系统，涵盖采购、库存、财务、人事等模块，"
        "各模块之间有复杂的审批流程和严格的数据依赖关系。",
        {"complex_business": True, "strict_consistency": True},
    ),
    (
        "军工单位指挥系统，要求全部部署在内部网络，不能连接外网，"
        "所有数据必须存储在本地服务器上，需满足等保三级要求。",
        {"deployment_constraint": True, "security": True},
    ),
    # 示例11: 教会 LLM "简单增删改查"→极简业务 (简单CRUD, 无需复杂架构)
    (
        "面向内部员工的后台管理系统，主要就是增删改查和表单录入，"
        "不涉及复杂业务逻辑，并发量也很低。",
        {"simple_crud": True, "deployment_constraint": True},
    ),
    # 示例12: 教会 LLM "预算有限/小团队"→资源受限 (成本约束, 避免重型架构)
    (
        "创业团队的第一个MVP版本，预算有限，团队只有5个人，"
        "希望尽量免运维、快速上线验证想法。",
        {"resource_constrained": True, "scalability": False},
    ),
    # 示例13: 教会 LLM "日终批量处理"→数据密集型+资源受限 (批处理场景)
    (
        "银行日终结算系统，每天凌晨批量处理当天的交易数据，"
        "生成对账报表和监管报送文件，不需要实时响应。",
        {"data_intensive": True, "resource_constrained": True, "real_time": False},
    ),
    # 示例14: 教会 LLM "规则引擎"→复杂业务 (规则系统场景)
    (
        "保险核保风控系统，根据业务规则库自动判定风险等级和保费系数，"
        "规则需要由业务人员频繁调整，无需改代码就能上线新规则。",
        {"complex_business": True, "security": True},
    ),
    # 示例15: 教会 LLM "数据中台/数据湖"→数据密集型+可扩展 (仓库风格)
    (
        "企业数据中台，整合ERP、CRM、供应链等多个业务系统的数据，"
        "构建统一数据仓库，支持BI分析和多维报表查询。",
        {"data_intensive": True, "scalability": True},
    ),
]



def build_few_shot_prompt(user_requirement: str) -> str:
    """构建含 10 个 few-shot 示例的语义补全 prompt."""
    zh_labels = ", ".join(FEATURE_LABELS_ZH.values())

    shot_lines = ["以下是一些需求分析的示例，请参考它们的判断方式：", ""]
    for i, (text, labels) in enumerate(EXAMPLES, 1):
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
