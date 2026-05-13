# 学习路线：架构风格智能助手

> 从课程大作业到面试作品 —— 5 个阶段彻底搞懂 Compound AI System 的完整构建。

---

## 学习路线图

```
你现在在这里
    ↓
Phase 1                    Phase 2                    Phase 3                    Phase 4                    Phase 5
项目背景与课程要求         微服务与系统架构           Agent 与混合推理           知识图谱与工程增强          测试、答辩与简历
=================         =================         =================         ====================       ================

L01 课程目标与服务定位 →  L05 C4 系统上下文       →  L09 requirements-agent →  L15 Neo4j 知识图谱     →  L20 自动验收体系
 |                         |                          |                          |                          |
L02 为什么不是聊天机器人 → L06 C4 容器级架构       →  L10 matching-agent     →  L16 Few-shot Prompt   →  L21 单元测试与回归
 |                         |                          |                          |                          |
L03 Compound AI System  → L07 API Gateway 双引擎   →  L11 evaluation-agent   →  L17 LLM 缓存系统      →  L22 答辩讲稿与演示
 |                         |                          |                          |                          |
L04 快速启动与演示体验    → L08 微服务划分与通信    →  L12 LangGraph 编排      →  L18 ADR 决策溯源      →  L23 简历 Bullet 撰写
                                                     |                          |                          |
                                                     L13 规则引擎核心          →  L19 组合推荐与重构     →  L24 STAR 面试法
                                                     |
                                                     L14 LLM 降级与高可用
```

### 学习时间估算

| 路径 | 时长 | 适合人群 | 达成目标 |
|------|------|---------|---------|
| 快速通关 | 3 天 | 课程答辩在即，需要快速掌握全貌 | 能讲清系统架构和核心亮点，演示流畅 |
| 系统学习 | 7 天 | 想深入理解每个模块的实现细节 | 掌握混合推理、降级策略，能回答技术追问 |
| 深入复盘 | 14 天 | 准备将项目写入简历，应对面试深挖 | 能逐行讲解源码，理解每个 fallback 设计的取舍 |

---

## 3 天快速通关路线

| 天数 | 学习内容 | 重点 |
|------|---------|------|
| Day 1 | L01-L04（入门）+ L05-L07（架构概览） | 理解系统"做什么"和"怎么做" |
| Day 2 | L09（需求提取）+ L13（规则引擎）+ L15（知识图谱） | 掌握核心推理链路的三个关键环节 |
| Day 3 | L22（答辩讲稿）+ L23（简历 Bullet）+ L24（STAR 面试法） | 准备好演示和问答 |

---

## 7 天系统学习路线

| 天数 | 学习内容 |
|------|---------|
| Day 1 | L01-L04：课程要求 + Compound AI 概念 + 快速跑通系统 |
| Day 2 | L05-L08：C4 模型 + 微服务划分 + API Gateway 双引擎 + 服务间通信 |
| Day 3 | L09-L11：requirements-agent + matching-agent + evaluation-agent 源码精读 |
| Day 4 | L12-L14：LangGraph 编排 + 规则引擎评分逻辑 + LLM 降级全链路 |
| Day 5 | L15-L17：Neo4j 图模型 + Few-shot Prompt + LLM 缓存 |
| Day 6 | L18-L19：ADR 决策溯源 + 组合推荐 + 重构建议 |
| Day 7 | L20-L24：自动验收 + 单元测试 + 答辩讲稿 + 简历 + STAR 面试稿 |

---

## 14 天深入复盘路线

| 天数 | 学习内容 |
|------|---------|
| Day 1 | L01-L02：课程背景 + 系统定位 + 竞品对比 |
| Day 2 | L03-L04：Compound AI System 理论 + 项目跑通 + 4 个演示输入实测 |
| Day 3 | L05-L06：C4 Context → C4 Container 逐层绘制 + 架构风格选型理由 |
| Day 4 | L07-L08：API Gateway 双引擎源码 + 微服务通信 + Docker Compose 编排 |
| Day 5 | L09：requirements-agent 完整源码 + 关键词词典设计 + 否定过滤 |
| Day 6 | L10：matching-agent 评分函数 + 7 条规则 + 主流优先逻辑 |
| Day 7 | L11：evaluation-agent 混合推理 + LLM 投票/摘要 + 对比矩阵生成 |
| Day 8 | L12-L13：LangGraph StateGraph 构建 + 规则引擎与 LLM 的职责划分 |
| Day 9 | L14：全链路 LLM 降级测试 + 规则 only 模式验证 |
| Day 10 | L15：Neo4j 图模型 + Cypher 查询 + JSON fallback 机制 |
| Day 11 | L16-L17：9 个 Few-shot 示例设计思路 + 双后端缓存实现 |
| Day 12 | L18-L19：ADR 自动生成 + 组合推荐评分公式 + 5 种重构模式 |
| Day 13 | L20-L21：43 项自动验收脚本 + 76 条单元测试 + 20 条回归用例 |
| Day 14 | L22-L24：答辩逐字稿练习 + 简历多版本撰写 + STAR 场景模拟 |

---

## Phase 1 · 项目背景与课程要求

> 从"这个项目是什么"开始，到理解它和普通 LLM 聊天机器人的本质区别

| 序号 | 课程 | 主题 | 关键概念 | 预计时长 |
|------|------|------|---------|---------|
| L01 | 课程目标与服务定位 | 大作业要求 → 系统定位 → 设计闭环 | 9 项技术建议、43 项验收标准、C/S 评分 | 30min |
| L02 | 为什么不是聊天机器人 | 一般 LLM 问答 vs 复合 AI 推理系统 | 规则引擎主导、LLM 辅助、知识图谱增强 | 45min |
| L03 | Compound AI System 思想 | 多 Agent 协作、混合推理、降级设计 | Compound AI、Multi-Agent、Graceful Degradation | 45min |
| L04 | 快速启动与演示体验 | 3 条命令跑通 → 4 组演示输入实测 | docker compose、Neo4j 初始化、env 配置 | 30min |

### L01 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [README.md](../README.md) | 系统概览、技术建议覆盖表、API 端点 |
| 必读 | [docs/00-迭代完成记录与要求映射.md](../docs/00-迭代完成记录与要求映射.md) | 9 项技术建议与代码的对应关系 |
| 选读 | [docs/大作业完成情况检查表.md](../docs/大作业完成情况检查表.md) | 作业评分标准逐条对照 |

**L01 面试问题**：
- Q: 这个系统解决了什么问题？
- Q: 为什么说它不是"又一个 LLM 聊天机器人"？
- Q: 你如何证明系统满足了课程的所有要求？

---

### L02 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docs/01-需求规格说明书.md](../docs/01-需求规格说明书.md) | 功能性需求与非功能需求的完整定义 |
| 必读 | [docs/02-架构设计文档.md](../docs/02-架构设计文档.md) | 设计目标、C4 模型、技术选型理由 |
| 选读 | [docs/ADR机制说明.md](../docs/ADR机制说明.md) | ADR 机制的设计动机 |

**L02 面试问题**：
- Q: 为什么不直接问 ChatGPT "我的系统该用什么架构"？
- Q: Compound AI System 和普通 LLM Application 的区别是什么？
- Q: 你的系统在哪几个环节使用了 LLM？为什么不是全部用？

---

### L03 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/api_gateway/app/langchain_workflow.py](../services/api_gateway/app/langchain_workflow.py) | LangGraph StateGraph 的节点定义 |
| 必读 | [services/api_gateway/app/main.py:53-61](../services/api_gateway/app/main.py#L53-L61) | 双引擎编排的启动逻辑 |
| 选读 | [services/evaluation_agent/app/main.py:279-284](../services/evaluation_agent/app/main.py#L279-L284) | `asyncio.gather` 并行调用 LLM |

**L03 面试问题**：
- Q: 什么是 Compound AI System？用你的项目举例说明。
- Q: 你的系统中哪些是"规则"、哪些是"学习"、哪些是"检索"？
- Q: 如果 LLM 挂了，系统的哪些功能会受影响？

---

### L04 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docker-compose.yml](../docker-compose.yml) | 容器编排、依赖关系、环境变量 |
| 必读 | [.env.example](../.env.example) | LLM_API_BASE/KEY/MODEL 配置 |
| 必读 | [README.md 演示输入部分](../README.md) | 4 组预设输入与预期输出 |
| 动手 | 运行 `docker compose up --build` | 实测 4 组输入，观察前端 11 个展示区 |

**L04 面试问题**：
- Q: 系统启动需要几步？哪些步骤是可选的？
- Q: 如果不配 LLM，系统还能正常运行吗？
- Q: 为什么选择这 4 组演示输入？它们各自展示了什么能力？

---

## Phase 2 · 微服务与系统架构

> 从系统自身的架构设计入手，理解 C4 模型和微服务划分

| 序号 | 课程 | 主题 | 关键概念 | 预计时长 |
|------|------|------|---------|---------|
| L05 | C4 系统上下文 | Context 图 → Container 图 → 外部系统边界 | C4 Model、系统边界、用户角色 | 30min |
| L06 | C4 容器级架构 | 7 个容器 → 职责划分 → 技术栈选型 | FastAPI、Nginx、Neo4j、Docker | 45min |
| L07 | API Gateway 双引擎 | LangGraph StateGraph + 手动 fallback | StateGraph、节点定义、workflow_trace | 60min |
| L08 | 微服务划分与通信 | 6 个微服务 → 同步 HTTP → 容错设计 | 微服务拆分原则、服务发现、故障隔离 | 45min |

### L05 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docs/02-架构设计文档.md — §2.3 C4-Context](../docs/02-架构设计文档.md) | 系统上下文图：用户 ↔ 系统 ↔ LLM |
| 必读 | [docs/02-架构设计文档.md — §2.1 架构风格选择](../docs/02-架构设计文档.md) | 为什么系统自身选微服务架构 |
| 选读 | [docs/PPT大纲.md](../docs/PPT大纲.md) | 答辩 PPT 的架构展示结构 |

**L05 面试问题**：
- Q: 画一下系统的 C4-Context 图。
- Q: 系统的外部依赖有哪些？每个是不可或缺的吗？
- Q: 你自己这个系统的架构风格是什么？为什么选它？

---

### L06 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docker-compose.yml](../docker-compose.yml) | 7 个容器完整定义 |
| 必读 | [docs/02-架构设计文档.md — §2.2 系统组成](../docs/02-架构设计文档.md) | ASCII 架构图 + 容器职责表 |
| 选读 | [docs/02-架构设计文档.md — §3 微服务详细设计](../docs/02-架构设计文档.md) | 每个微服务的详细设计 |

**L06 面试问题**：
- Q: 7 个容器各自是什么？端口怎么分配的？
- Q: 为什么分成 requirements / matching / evaluation 三个 Agent？
- Q: frontend 的技术栈为什么选原生 HTML 而不是 React？

---

### L07 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/api_gateway/app/main.py:53-61](../services/api_gateway/app/main.py#L53-L61) | 双引擎启动逻辑 |
| 必读 | [services/api_gateway/app/langchain_workflow.py:130-166](../services/api_gateway/app/langchain_workflow.py#L130-L166) | `build_workflow()` 完整实现 |
| 必读 | [services/api_gateway/app/workflow_state.py](../services/api_gateway/app/workflow_state.py) | TypedDict 状态定义 |
| 必读 | [services/api_gateway/app/main.py:88-140](../services/api_gateway/app/main.py#L88-L140) | 手动编排 `_manual_orchestrate()` |

**L07 面试问题**：
- Q: LangGraph 在你的系统中起什么作用？
- Q: 如果 LangGraph 没安装，系统怎么办？
- Q: workflow_trace 记录了什么？有什么用途？

---

### L08 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docker-compose.yml:3-24](../docker-compose.yml#L3-L24) | api-gateway depends_on 配置 |
| 必读 | [services/api_gateway/app/main.py:47-51](../services/api_gateway/app/main.py#L47-L51) | 服务地址环境变量 |
| 必读 | [services/matching_agent/app/main.py:20](../services/matching_agent/app/main.py#L20) | matching 调 knowledge-base 的 URL |
| 选读 | [services/api_gateway/app/main.py:192-210](../services/api_gateway/app/main.py#L192-L210) | 重构建议的"失败不阻塞"调用 |

**L08 面试问题**：
- Q: 服务之间怎么通信？为什么选同步 HTTP？
- Q: 如果 matching-agent 挂了，api-gateway 会怎样？
- Q: refactoring-agent 调用失败会影响推荐结果吗？为什么？

---

## Phase 3 · Agent 与混合推理

> 逐个精读 3 个核心 Agent 的源码，理解"规则 + 图谱 + LLM"三层混合推理

| 序号 | 课程 | 主题 | 关键概念 | 预计时长 |
|------|------|------|---------|---------|
| L09 | requirements-agent | 关键词词典 → 否定过滤 → LLM 语义补全 | 10 维特征、90 个关键词、6 个否定模式 | 60min |
| L10 | matching-agent | 规则引擎评分 → 图谱融合 → 主流优先 | score_style()、blend_scores()、7 条规则 | 60min |
| L11 | evaluation-agent | 混合推理 → LLM 投票/摘要 → 对比矩阵 → 风险分析 | asyncio.gather、_fallback_summary、STYLE_RISK_MAP | 60min |
| L12 | LangGraph 编排 | StateGraph 构建 → 节点实现 → 双引擎切换 | START/END、add_edge、ainvoke | 45min |
| L13 | 规则引擎核心 | 评分公式 → 7 条规则 → 学习权重 → 返回字段 | score_style()、learned_weights、MAINSTREAM_STYLES | 50min |
| L14 | LLM 降级与高可用 | 每节点的降级路径 → 全链路规则 only 测试 | Graceful Degradation、ImportError fallback、timeout | 40min |

### L09 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/requirements_agent/app/main.py:67-142](../services/requirements_agent/app/main.py#L67-L142) | 关键词词典 + 否定过滤 + LLM 补全 |
| 必读 | [services/requirements_agent/app/main.py:155-262](../services/requirements_agent/app/main.py#L155-L262) | lexicon 定义（10 维 × 90 词） |
| 选读 | [services/common/prompts/requirements_few_shot.py](../services/common/prompts/requirements_few_shot.py) | 6 个 Few-shot 示例 |

**L09 面试问题**：
- Q: 10 个特征维度是怎么设计的？为什么是这 10 个？
- Q: 否定过滤是怎么做的？举例说明。
- Q: LLM 语义补全什么时候触发？为什么设置"≤ 2 维"的阈值？
- Q: 如果用户说"不需要高并发"，系统会怎么处理？

---

### L10 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/matching_agent/app/main.py:44-101](../services/matching_agent/app/main.py#L44-L101) | `score_style()` 完整评分逻辑 |
| 必读 | [services/matching_agent/app/main.py:103-170](../services/matching_agent/app/main.py#L103-L170) | `/match` 端点：三层融合 + 主流优先 |
| 必读 | [services/matching_agent/app/graph_matcher.py:47-93](../services/matching_agent/app/graph_matcher.py#L47-L93) | `blend_scores()` 融合策略 |

**L10 面试问题**：
- Q: 一个风格的具体分数是怎么算出来的？
- Q: 为什么图谱加分有 50% 的上限？
- Q: 学习权重是怎么来的？目前有多少条数据？
- Q: 为什么 MAINSTREAM_STYLES 是这三个？

---

### L11 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/evaluation_agent/app/main.py:271-392](../services/evaluation_agent/app/main.py#L271-L392) | `evaluate()` 端点完整流程 |
| 必读 | [services/evaluation_agent/app/main.py:59-138](../services/evaluation_agent/app/main.py#L59-L138) | LLM 摘要 + 降级摘要 |
| 必读 | [services/evaluation_agent/app/main.py:141-181](../services/evaluation_agent/app/main.py#L141-L181) | LLM 投票机制 |
| 必读 | [services/evaluation_agent/app/main.py:252-268](../services/evaluation_agent/app/main.py#L252-L268) | STYLE_RISK_MAP 风险模板 |
| 选读 | [services/common/prompts/evaluation_few_shot.py](../services/common/prompts/evaluation_few_shot.py) | 3 个评估报告 Few-shot 示例 |

**L11 面试问题**：
- Q: LLM 投票和 LLM 摘要是串行还是并行执行的？为什么？
- Q: LLM 投票的 temperature 是多少？为什么？
- Q: 降级摘要 `_fallback_summary()` 能做到什么程度？
- Q: 对比矩阵里每行有哪些字段？
- Q: 风险分析里的 risk 和建议是怎么生成的？

---

### L12 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/api_gateway/app/langchain_workflow.py:130-166](../services/api_gateway/app/langchain_workflow.py#L130-L166) | `build_workflow()` 完整构建 |
| 必读 | [services/api_gateway/app/langchain_workflow.py:33-113](../services/api_gateway/app/langchain_workflow.py#L33-L113) | 3 个节点的实现 |
| 必读 | [services/api_gateway/app/workflow_state.py](../services/api_gateway/app/workflow_state.py) | TypedDict 各字段含义 |
| 必读 | [services/api_gateway/app/main.py:144-163](../services/api_gateway/app/main.py#L144-L163) | LangGraph 编排的调用方式 |

**L12 面试问题**：
- Q: StateGraph 的状态是怎么在各节点间传递的？
- Q: 为什么选择 LangGraph 而不是 LangChain 的 Chain？
- Q: trace 节点做了什么？有什么实际用途？
- Q: 如果让你加一个条件路由（比如检测到特定需求走不同路径），你会怎么改？

---

### L13 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/matching_agent/app/main.py:44-67](../services/matching_agent/app/main.py#L44-L67) | 基础评分（tags + 学习权重） |
| 必读 | [services/matching_agent/app/main.py:64-86](../services/matching_agent/app/main.py#L64-L86) | 7 条硬编码专业规则 |
| 必读 | [services/matching_agent/app/main.py:88-101](../services/matching_agent/app/main.py#L88-L101) | 返回值结构 |
| 必读 | [services/matching_agent/app/main.py:132-151](../services/matching_agent/app/main.py#L132-L151) | 主流优先 + Top 3 选取逻辑 |

**L13 面试问题**：
- Q: 7 条硬编码规则各是什么？为什么需要它们？
- Q: 每条规则加 1 分，为什么不加更多？
- Q: 学习权重和硬编码规则同时生效时，会不会重复加分？
- Q: 如果你想新增一条规则（比如 Microservices 适合 team_size_large），加在哪里？

---

### L14 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/requirements_agent/app/main.py:86-94](../services/requirements_agent/app/main.py#L86-L94) | LLM 特征补全的降级：无 LLM 直接返回 |
| 必读 | [services/matching_agent/app/main.py:114-121](../services/matching_agent/app/main.py#L114-L121) | 学习权重获取的降级：不可用则跳过 |
| 必读 | [services/matching_agent/app/graph_matcher.py:43-45](../services/matching_agent/app/graph_matcher.py#L43-L45) | 图谱证据的降级：返回 None |
| 必读 | [services/evaluation_agent/app/main.py:59-61](../services/evaluation_agent/app/main.py#L59-L61) | LLM 摘要的降级：`_fallback_summary()` |
| 必读 | [services/api_gateway/app/main.py:181-188](../services/api_gateway/app/main.py#L181-L188) | LangGraph 运行时异常 fallback |
| 动手 | 注释掉 .env 中的 LLM 配置，运行回归测试 | 验证规则 only 模式是否正常 |

**L14 面试问题**：
- Q: 画出全链路的 LLM 降级路径图。
- Q: 核心推荐链路（extract → match → evaluate）中哪些步骤完全不依赖 LLM？
- Q: 如果两个 LLM 调用点都失败，最终报告长什么样？
- Q: 为什么"降级"比"报错"更好？

---

## Phase 4 · 知识图谱与工程增强

> Neo4j 图模型 + Few-shot Prompt 设计 + 缓存系统 + ADR + 组合推荐 + 重构建议

| 序号 | 课程 | 主题 | 关键概念 | 预计时长 |
|------|------|------|---------|---------|
| L15 | Neo4j 知识图谱 | 图模型 → Cypher 查询 → JSON fallback | 6 节点 + 6 关系、HAS_QUALITY、COMPLEMENTS | 60min |
| L16 | Few-shot Prompt Engineering | 9 个示例的设计思路 → 降级机制 | requirements 6 + evaluation 3、零样本 fallback | 45min |
| L17 | LLM 缓存系统 | 双后端缓存 → 键生成 → 自动失效 | 内存/SQLite、knowledge_version、SHA256 | 50min |
| L18 | ADR 决策溯源 | 自动生成 → 双存储 → API 查询 | ADR-YYYYMMDD-NNN、Neo4j 同步、容错 | 40min |
| L19 | 组合推荐与重构建议 | 5 种组合 → 评分公式 → 5 种重构模式 | combo_matcher、坏味检测、Strangler Fig | 60min |

### L15 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/knowledge_base/app/graph_repository.py:22-48](../services/knowledge_base/app/graph_repository.py#L22-L48) | `_get_driver()` + `_run_query()` |
| 必读 | [services/knowledge_base/app/graph_repository.py:247-319](../services/knowledge_base/app/graph_repository.py#L247-L319) | `graph_match()` 核心图谱推理 |
| 必读 | [services/knowledge_base/app/json_repository.py:40-43](../services/knowledge_base/app/json_repository.py#L40-L43) | `get_styles()` JSON 读取 |
| 必读 | [services/knowledge_base/init/init_neo4j.py](../services/knowledge_base/init/init_neo4j.py) | 图模型初始化脚本 |
| 必读 | [services/knowledge_base/app/main.py:21-51](../services/knowledge_base/app/main.py#L21-L51) | 双后端调度 `_repo()` |
| 选读 | [services/knowledge_base/data/architecture_styles.json](../services/knowledge_base/data/architecture_styles.json) | 10 种风格完整数据 |

**L15 面试问题**：
- Q: Neo4j 图模型有哪些节点类型和关系类型？
- Q: `graph_match()` 的查询逻辑是什么？
- Q: `KNOWLEDGE_BACKEND=auto` 是什么意思？有哪些可选值？
- Q: JSON 存储和 Neo4j 存储有什么不同的优势？

---

### L16 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/common/prompts/requirements_few_shot.py:28-54](../services/common/prompts/requirements_few_shot.py#L28-L54) | 6 个示例的场景覆盖 |
| 必读 | [services/common/prompts/requirements_few_shot.py:57-86](../services/common/prompts/requirements_few_shot.py#L57-L86) | `build_few_shot_prompt()` 构建逻辑 |
| 必读 | [services/common/prompts/evaluation_few_shot.py:10-80](../services/common/prompts/evaluation_few_shot.py#L10-L80) | 3 个完整报告示例 |
| 必读 | [services/requirements_agent/app/main.py:98-104](../services/requirements_agent/app/main.py#L98-L104) | Few-shot 的 ImportError 降级 |

**L16 面试问题**：
- Q: 需求的 6 个 Few-shot 示例分别覆盖了什么场景？
- Q: 为什么需要 Few-shot？零样本有什么不足？
- Q: Few-shot 模块加载失败怎么办？
- Q: Prompt 中为什么要求"输出严格的 JSON 格式"？

---

### L17 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/common/cache/simple_cache.py](../services/common/cache/simple_cache.py) | 内存缓存实现：TTL + 线程安全 |
| 必读 | [services/common/cache/sqlite_cache.py](../services/common/cache/sqlite_cache.py) | SQLite 持久化缓存 |
| 必读 | [services/common/cache/hash_utils.py:29-36](../services/common/cache/hash_utils.py#L29-L36) | `cache_key()` 生成逻辑 |
| 必读 | [services/common/cache/hash_utils.py:10-22](../services/common/cache/hash_utils.py#L10-L22) | `knowledge_version()` 版本计算 |
| 必读 | [services/api_gateway/app/main.py:166-220](../services/api_gateway/app/main.py#L166-L220) | 缓存读取和写入的调用位置 |

**L17 面试问题**：
- Q: 缓存键是怎么生成的？为什么包含 model 和 knowledge_version？
- Q: knowledge_version 什么时候会变？变了之后缓存会怎样？
- Q: 内存缓存和 SQLite 缓存各适合什么场景？
- Q: 如果用户改了 architecture_styles.json，缓存会自动失效吗？

---

### L18 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/knowledge_base/app/json_repository.py:158-196](../services/knowledge_base/app/json_repository.py#L158-L196) | ADR JSON 存储：ID 生成 + 写入 |
| 必读 | [services/knowledge_base/app/graph_repository.py:332-377](../services/knowledge_base/app/graph_repository.py#L332-L377) | ADR Neo4j 同步 |
| 必读 | [services/evaluation_agent/app/main.py:350-392](../services/evaluation_agent/app/main.py#L350-L392) | ADR 自动触发生成 |
| 必读 | [services/knowledge_base/app/main.py:186-227](../services/knowledge_base/app/main.py#L186-L227) | ADR API 端点 |

**L18 面试问题**：
- Q: 什么是 ADR？你的项目中 ADR 怎么生成的？
- Q: ADR ID 的格式是什么？为什么这样设计？
- Q: ADR 写入失败了会怎样？会影响推荐结果吗？
- Q: ADR 中存储了哪些信息？

---

### L19 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [services/matching_agent/app/combo_matcher.py:28-98](../services/matching_agent/app/combo_matcher.py#L28-L98) | `score_combination()` 完整评分 |
| 必读 | [services/knowledge_base/data/architecture_combinations.json](../services/knowledge_base/data/architecture_combinations.json) | 5 种组合模式定义 |
| 必读 | [services/refactoring_agent/app/main.py:58-84](../services/refactoring_agent/app/main.py#L58-L84) | ARCHITECTURE_SMELLS 定义 |
| 必读 | [services/refactoring_agent/app/main.py:88-144](../services/refactoring_agent/app/main.py#L88-L144) | REFACTORING_PATTERNS 5 种模式 |
| 必读 | [services/refactoring_agent/app/main.py:195-257](../services/refactoring_agent/app/main.py#L195-L257) | `build_rule_template()` 规则模板生成 |

**L19 面试问题**：
- Q: 组合推荐的评分公式是什么？每个加分项的含义？
- Q: CQRS + Event Sourcing 的复杂度惩罚为什么是 3？
- Q: 重构建议什么时候触发？触发条件是什么？
- Q: Strangler Fig Pattern 的 4 步分别是什么？

---

## Phase 5 · 测试、答辩与简历

> 从验证系统正确性到展示个人能力，完成"技术 → 表达 → 求职"的最后一公里

| 序号 | 课程 | 主题 | 关键概念 | 预计时长 |
|------|------|------|---------|---------|
| L20 | 自动验收体系 | 43 项验收脚本 → 7 大类检查 | check_assignment.py、Markdown+JSON 双输出 | 40min |
| L21 | 单元测试与回归测试 | 76 单元测试 + 20 回归用例 | pytest、5 维验证、datasets/requirements_cases.json | 50min |
| L22 | 答辩讲稿与演示 | 5min 演示 + 15min 讲解 + 5min 问答 | 4 组演示、逐步讲解、技术亮点话术 | 90min |
| L23 | 简历 Bullet 撰写 | 简洁版/标准版/详细版/岗位版 | 量化指标、技术关键词、层次感 | 60min |
| L24 | STAR 面试法 | 30s/1min/3min 自我介绍 + 7 场景 STAR | S/T/A/R 黄金比例、分模块话术 | 90min |

### L20 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [scripts/check_assignment.py](../scripts/check_assignment.py) | 43 项检查的脚本实现 |
| 必读 | [docs/自动验收检查结果.md](../docs/自动验收检查结果.md) | 43 项全部通过的结果详情 |
| 必读 | [docs/技术建议符合度报告.md](../docs/技术建议符合度报告.md) | 9 项技术建议的逐项对照 |

**L20 面试问题**：
- Q: 43 项验收检查覆盖了哪些方面？
- Q: 如果今天重新运行 check_assignment.py，通过率是多少？
- Q: 自动验收能发现什么问题？

---

### L21 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [tests/unit/test_matching.py](../tests/unit/test_matching.py) | 规则引擎 + 图谱融合 + 组合推荐测试 |
| 必读 | [tests/unit/test_gateway.py](../tests/unit/test_gateway.py) | 缓存键 + 双引擎切换测试 |
| 必读 | [tests/datasets/requirements_cases.json](../tests/datasets/requirements_cases.json) | 20 条回归测试用例 |
| 必读 | [tests/run_regression.py:22-41](../tests/run_regression.py#L22-L41) | `evaluate_response()` 5 维验证逻辑 |
| 选读 | [tests/run_smoke.py](../tests/run_smoke.py) | 冒烟测试 |
| 选读 | [tests/conftest.py](../tests/conftest.py) | Pytest 配置 |

**L21 面试问题**：
- Q: 回归测试的 5 个验证维度分别是什么？
- Q: 测试用例是怎么设计的？覆盖了哪些场景？
- Q: 单元测试和回归测试的区别？
- Q: 如果改了一行代码，你如何确保没有破坏功能？

---

### L22 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docs/答辩讲稿.md](../docs/答辩讲稿.md) | 完整答辩讲稿（5+15+5 min） |
| 必读 | [docs/答辩讲稿_技术建议完整版.md](../docs/答辩讲稿_技术建议完整版.md) | 9 项技术建议的逐条讲解话术 |
| 必读 | [docs/07-答辩讲稿与问答.md（如存在）](../docs/) | 常见答辩追问与应对 |
| 必读 | [docs/答辩PPT.md](../docs/答辩PPT.md) | PPT 结构和大纲 |
| 动手 | 对着镜子计时演练完整讲稿 | 控制时间在 5min 演示 + 15min 讲解 |

**L22 面试问题（模拟答辩追问）**：
- Q: 你在这个项目中最大的技术挑战是什么？
- Q: 如果有更多时间，你会在哪些方面改进？
- Q: 为什么要用规则引擎而不是训练一个分类模型？
- Q: 你觉得系统的哪个模块设计得最好？哪个最弱？

---

### L23 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docs/resume_learning/项目素材池.md](项目素材池.md) | §7 可写进简历的量化指标 |
| 必读 | 本文档 Phase 1-4 的技术亮点 | 提炼 3-5 句简历描述 |
| 动手 | 撰写简历 Bullet | 对照素材池 §7 的量化指标 |

**简历 Bullet 模板**：

**简洁版（1-2 行）**：
> 设计并实现 Compound AI 架构推荐系统，6 个 FastAPI 微服务 + LangGraph 编排，集成 Neo4j 知识图谱推理和 LLM 混合决策，支持组合推荐和重构建议。LLM 不可用时自动降级保证核心链路高可用。

**标准版（3-4 行）**：
> **架构风格智能助手 — LLM + 知识图谱双驱动架构推荐系统**
> - 基于 FastAPI 构建 6 个独立微服务（需求提取 / 规则匹配 / LLM 评估 / 知识库 / 重构建议），Docker Compose 编排
> - 使用 LangGraph StateGraph 编排 Agent 协作流程，规则引擎（7 条架构规则 + 10 维关键词词典）主导评分，LLM 作为语义补全和投票增强
> - 集成 Neo4j 知识图谱（6 节点 + 6 关系）进行关系推理，自动生成 ADR 决策记录；实现内存/SQLite 双后端请求缓存
> - 43 项自动验收 100% 通过，76 条单元测试覆盖全部模块，20 条回归用例覆盖典型架构场景

**详细版（5-6 行）**：
> **架构风格智能助手 — 端到端 Compound AI System**
> - 基于 FastAPI + LangGraph 构建 6 个微服务 Agent 系统，实现"自然语言需求 → 特征提取 → 规则+图谱匹配 → LLM 评估 → 可解释报告"的完整闭环
> - requirements-agent：10 维质量属性关键词词典（约 90 词）+ 6 种否定语义过滤 + Few-shot LLM 语义补全
> - matching-agent：规则引擎评分（标签匹配 + 7 条架构规则 + 学习权重）+ Neo4j 图谱推理（HAS_QUALITY 关系遍历）+ 组合评分（5 种预定义组合模式）
> - evaluation-agent：规则排序 + LLM 投票/摘要（asyncio.gather 并行）+ 风险分析（3 种风格专属模板）+ ADR 自动生成
> - 工程增强：内存/SQLite 双后端请求缓存（SHA256 键 + knowledge_version 自动失效）、Few-shot Prompt（9 示例）、5 种重构模式检测
> - 全链路 LLM 可选：每节点均有降级路径，LLM 不可用时自动切换规则模式保证核心链路高可用

**L23 面试问题**：
- Q: 你用哪些量化指标来描述这个项目？
- Q: 简历中为什么要强调"降级"和"fallback"？
- Q: 你怎么向非技术背景的人介绍这个项目？

---

### L24 阅读清单

| 类型 | 文件 | 阅读要点 |
|------|------|---------|
| 必读 | [docs/resume_learning/参考仓库learn-minimind设计分析.md](参考仓库learn-minimind设计分析.md) | §5 STAR 面试法设计 |
| 必读 | [docs/答辩讲稿.md](../docs/答辩讲稿.md) | 完整答辩讲稿（作为"3 分钟项目介绍"的参考） |
| 动手 | 撰写并背诵 30s / 1min / 3min 自我介绍 | 见下方模板 |
| 动手 | 准备 7 个技术难点的 STAR 话术 | 见下方场景表 |

**自我介绍模板**：

**30 秒版本（电梯演讲）**：
> 我独立完成了一个 LLM + 知识图谱双驱动的架构风格智能助手。系统用 6 个 FastAPI 微服务 + LangGraph 编排，能根据自然语言需求自动推荐架构风格并生成可解释的决策报告。核心亮点是规则引擎主导 + LLM 增强 + Neo4j 图谱推理的三层混合架构，LLM 不可用时自动降级保证核心链路高可用。43 项自动验收 100% 通过。

**1 分钟版本（常规面试）**：
> 我做的项目是架构风格智能助手，一个 Compound AI System。用户输入软件需求，系统自动完成特征提取、风格匹配、评估决策，生成包含推荐理由、对比矩阵、风险分析的完整报告。
>
> **架构方面**，系统自身采用微服务架构，6 个独立 FastAPI 容器通过 Docker Compose 编排。使用 LangGraph StateGraph 编排 Agent 的协作流程，LangGraph 不可用时自动回退到手写编排。
>
> **推理方面**，核心是三层混合推理：requirements-agent 用 10 维关键词词典做特征提取；matching-agent 用规则引擎（7 条架构规则）和 Neo4j 知识图谱做风格匹配；evaluation-agent 用规则排序加 LLM 投票/摘要做最终决策。
>
> **工程方面**，全链路 LLM 可选，每个节点都有降级路径。实现了内存/SQLite 双后端缓存、ADR 自动生成、组合推荐和重构建议。76 条单元测试、20 条回归用例、43 项自动验收全部通过。

**STAR 分模块话术**：
对照 [项目素材池.md §8](项目素材池.md) 中的薄弱点，为以下 7 个场景准备 STAR 应对：

| 场景 | S（情境） | T（任务） | A（行动） | R（结果） |
|------|----------|----------|----------|----------|
| 为什么用规则引擎而不是纯 LLM | 课程要求可解释性 | 保证评分可追溯 | score_style() 透明计分 | 每条推荐都有命中标签和规则理由 |
| LangGraph 编排设计 | 多 Agent 需要协调 | 实现服务编排 | StateGraph + 双引擎 fallback | workflow_trace 全程可观测 |
| Neo4j 图谱设计 | 需要展示图推理能力 | 设计知识图谱模型 | 6 节点 + 6 关系 | 图谱推理增强规则评分，有 50% cap |
| LLM 降级设计 | LLM 服务不稳定 | 核心链路不能中断 | 每节点 try/except + fallback | 不配 LLM 也能正常运行 |
| 缓存系统设计 | 重复请求浪费 LLM token | 实现请求级缓存 | 双后端 + knowledge_version | 缓存命中时响应 < 10ms |
| 测试策略 | 课程要求严谨验证 | 建立完整测试体系 | 单元 + 回归 + 冒烟 + 自动验收 | 43/43 验收通过 |
| 组合推荐实现 | 单一风格不够用 | 实现多风格组合评分 | 4 因素评分公式 | 5 种组合模式可用 |

---

## 附录 A：关键代码阅读顺序

如果只能读 10 个文件，按这个顺序读：

1. [README.md](../README.md) — 建立全局认知
2. [docker-compose.yml](../docker-compose.yml) — 理解部署架构
3. [services/api_gateway/app/main.py](../services/api_gateway/app/main.py) — 入口 + 编排 + 缓存
4. [services/api_gateway/app/langchain_workflow.py](../services/api_gateway/app/langchain_workflow.py) — LangGraph 核心
5. [services/requirements_agent/app/main.py](../services/requirements_agent/app/main.py) — 特征提取
6. [services/matching_agent/app/main.py](../services/matching_agent/app/main.py) — 规则引擎
7. [services/matching_agent/app/graph_matcher.py](../services/matching_agent/app/graph_matcher.py) — 图谱融合
8. [services/evaluation_agent/app/main.py](../services/evaluation_agent/app/main.py) — 混合推理
9. [services/knowledge_base/app/json_repository.py](../services/knowledge_base/app/json_repository.py) — JSON 存储
10. [services/refactoring_agent/app/main.py](../services/refactoring_agent/app/main.py) — 重构建议

---

## 附录 B：面试快速检索表

| 被问到 | 阅读 |
|--------|------|
| 项目整体介绍 | L01 + L22 (答辩讲稿) |
| 系统架构是什么 | L05-L08 (Phase 2) |
| LLM 怎么用的 | L14 (降级与高可用) |
| 知识图谱做了什么 | L15 (Neo4j) |
| 规则引擎怎么设计 | L13 (规则引擎核心) |
| 测试怎么做的 | L20-L21 (验收 + 测试) |
| 遇到什么困难 | L14 (降级设计) + L19 (组合推荐) |
| 怎么保证可解释性 | L10 (规则评分) + L18 (ADR) |
| 如果 LLM 挂了 | L14 (全链路降级) |
| 简历上写的技术深度 | L23 (简历 Bullet) |
| 自我介绍 | L24 (STAR 面试法) |

---

## 附录 C：相关文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 项目素材池 | [项目素材池.md](项目素材池.md) | 所有量化指标的集合 |
| learn-minimind 分析 | [参考仓库learn-minimind设计分析.md](参考仓库learn-minimind设计分析.md) | 参考仓库的文档架构分析 |
| 架构设计文档 | [../02-架构设计文档.md](../docs/02-架构设计文档.md) | 完整的技术架构描述 |
| 需求规格说明书 | [../01-需求规格说明书.md](../docs/01-需求规格说明书.md) | 功能性/非功能性需求 |
| 测试报告 | [../03-系统测试报告.md](../docs/03-系统测试报告.md) | 测试结果和覆盖度 |
| 答辩讲稿 | [../答辩讲稿.md](../docs/答辩讲稿.md) | 答辩逐字稿 |
| 技术建议符合度 | [../技术建议符合度报告.md](../docs/技术建议符合度报告.md) | 9 项建议的逐条证据 |
| 自动验收结果 | [../自动验收检查结果.md](../docs/自动验收检查结果.md) | 43 项验收检查结果 |

---

<p align="center">
  <strong>从课程作业到面试作品 —— 不是"我做了什么"，而是"你怎么一步步理解并展示这个系统"。</strong>
</p>
