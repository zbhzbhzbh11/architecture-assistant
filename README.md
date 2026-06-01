# 架构风格智能助手

软件体系结构课程大作业。输入自然语言需求描述，经 LLM + Neo4j 知识图谱 + 规则引擎三层混合推理，输出 Top3 架构推荐、对比矩阵、风险建议、组合推荐与 ADR 决策记录。支持知识进化（反馈驱动的权重学习）和三级独立降级。

## 系统概览

| 服务 | 端口 | 职责 |
|------|------|------|
| api-gateway | 8000 | LangGraph StateGraph 编排 + 手动 fallback + 请求级缓存 |
| requirements-agent | 8001 | LLM 优先语义分析 + 12 维特征词典溯源 + 否定语义过滤 + 纯规则降级 |
| matching-agent | 8002 | 规则引擎四层评分（10 条专家规则）+ Neo4j 图谱证据融合 + 组合推荐（8 种） |
| evaluation-agent | 8003 | Send() 并行 LLM 投票/摘要 + ADR 自动生成 + 混合推理 |
| knowledge-base | 8004 | Neo4j + JSON 双后端存储 + 反馈学习权重 + ADR 持久化 |
| refactoring-agent | 8005 | 架构坏味检测（5 种）+ 重构模式推荐（5 种）+ 迁移方案 |
| neo4j | 7474/7687 | 知识图谱数据库（可选，JSON fallback） |
| frontend | 3000 | 11 区结果展示（对比矩阵 / 拓扑图 / 图谱证据 / 组合 / 重构 / 工作流追踪 / ADR） |

## 快速启动

```bash
# 1. 配置 LLM（可选，不配置则纯规则模式运行）
cp .env.example .env
# 编辑 .env 填入 LLM_API_BASE / LLM_API_KEY / LLM_MODEL

# 2. 启动全部服务（首次加 --build）
docker compose up -d

# 3. 初始化 Neo4j 知识图谱（首次）
docker compose exec knowledge-base python init/init_neo4j.py

# 4. 浏览器打开
# http://localhost:3000
```

## 架构风格（14 种）

| 分类 | 风格 |
|------|------|
| **数据流** | 管道-过滤器（Pipeline-Filter）、批处理（Batch-Sequential） |
| **调用/返回** | 分层架构（Layered）、客户端-服务器（Client-Server）、面向对象（Object-Oriented） |
| **以数据为中心** | 仓库架构（Repository） |
| **虚拟机** | 规则系统（Rule-Based） |
| **独立构件** | 事件驱动（Event-Driven） |
| **现代/进阶** | 微服务（Microservices）、SOA、六边形架构（Hexagonal）、CQRS、Serverless、空间架构（Space-Based） |

## LLM 配置

```bash
# .env 文件
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=sk-xxxx
LLM_MODEL=deepseek-v4-flash
```

LLM 不配置时系统自动降级为纯规则模式，核心推荐链路不受影响。LLM 仅在规则确定的候选列表内做闭集投票（t=0.0），不参与候选生成。

## Neo4j 配置

```bash
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jneo4j
KNOWLEDGE_BACKEND=auto    # json / neo4j / auto
```

`auto` 模式优先 Neo4j，不可用时自动 fallback JSON。JSON 模式零外部依赖，全功能运行。

## 演示输入

推荐在答辩时依次使用以下输入，展示系统不同能力：

| # | 输入 | 展示重点 |
|---|------|---------|
| 1 | 开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话。 | **基础推荐**：Event-Driven |
| 2 | 构建电商平台，订单支付库存需要强一致事务，双十一高峰要抗压，多团队并行开发。 | **组合推荐**：Microservices + Event-Driven |
| 3 | 已有单体电商系统，订单库存耦合严重，性能瓶颈明显，希望拆分为微服务。 | **重构建议**：绞杀者模式 + 迁移方案 |
| 4 | 银行日终结算系统，批量处理当天交易生成对账报表，不需要实时响应，服务器配置不高。 | **批处理风格**：Batch-Sequential |
| 5 | 保险核保风控引擎，根据业务规则库自动判定风险等级，规则可由业务人员在线调整无需改代码。 | **规则系统**：Rule-Based |
| 6 | 企业数据中台，整合多个业务系统数据构建统一数据仓库，支持BI分析和多维报表。 | **仓库架构**：Repository |

## 技术建议覆盖

| 建议 | 状态 | 说明 |
|------|------|------|
| LLM + 知识图谱双驱动 | ✅ | 规则引擎(确定性基线) + Neo4j(关系推理) + LLM(语义增强) |
| LangGraph Multi-Agent | ✅ | 4 节点 StateGraph + Send() 声明式并行扇出 |
| Neo4j 图谱存储 | ✅ | 129 节点 / 193 关系 / 6 类节点 / 8 类关系 |
| Few-shot Prompt | ✅ | 15 个示例（12 需求分析 + 3 评估报告），零样本 fallback |
| 规则引擎校验 | ✅ | 四层评分（标签+学习权重+10 条专家规则+反向惩罚） |
| LLM 缓存 | ✅ | 内存/SQLite 双后端，SHA-256 键 + 知识库版本感知自动失效 |
| ADR 决策溯源 | ✅ | 自动生成，JSON+Neo4j 双端存储，API 可查询 |
| 组合推荐 | ✅ | 8 种预定义组合 + Neo4j COMPLEMENTS 动态发现 |
| 重构建议 | ✅ | 5 种坏味检测 + 5 种重构模式 + 渐进式迁移步骤 |
| 知识进化 | ✅ | 反馈→图遍历→时间衰减→归一化→LEARNED_FOR 同步，提交即生效 |
| 三级降级 | ✅ | LLM/Neo4j/LangGraph 独立降级，最坏情况仍 100% 可用 |

## 测试

```bash
# 单元测试（79 条）
pytest tests/unit/ -v

# 回归测试（24 条用例，需服务运行）
python tests/run_regression.py

# 冒烟测试
python tests/run_smoke.py

# 自动验收检查（43 项）
python scripts/check_assignment.py --project-root .
```

## 目录结构

```
architecture-assistant/
├── docker-compose.yml
├── services/
│   ├── common/
│   │   ├── cache/          # 请求级缓存（memory/SQLite）
│   │   ├── matching/       # 规则引擎 + 组合评分（核心算法）
│   │   └── prompts/        # Few-shot 示例（15 个）
│   ├── api-gateway/        # LangGraph 编排 + 手动 fallback
│   ├── requirements-agent/ # 特征提取（LLM + 词典）
│   ├── matching-agent/     # 规则 + 图谱 + 组合 + 学习权重
│   ├── evaluation-agent/   # LLM 投票/摘要 + ADR
│   ├── knowledge-base/     # Neo4j + JSON 双后端 + 反馈 + ADR
│   │   ├── init/           # init_neo4j.py
│   │   └── data/           # architecture_styles.json 等
│   └── refactoring-agent/  # 坏味检测 + 重构模式
├── frontend/               # 单页应用（Nginx + Mermaid.js）
├── tests/
│   ├── unit/               # 8 个测试模块
│   └── datasets/           # 24 条需求用例
├── docs/                   # 需求规格说明书 / 架构设计文档 / 系统测试报告
└── scripts/                # check_assignment.py
```
