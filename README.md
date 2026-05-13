# 架构风格智能助手

软件体系结构课程大作业。LLM + 知识图谱双驱动，LangGraph 微服务编排，支持组合推荐和重构建议。

## 系统概览

| 服务 | 端口 | 职责 |
|------|------|------|
| api-gateway | 8000 | LangGraph 编排 + 手动 fallback + 请求缓存 |
| requirements-agent | 8001 | 关键词匹配 + Few-shot LLM 语义补全 |
| matching-agent | 8002 | 规则引擎 + Neo4j 图谱关系推理 + 组合评分 |
| evaluation-agent | 8003 | LLM 投票/摘要 + ADR 自动生成 |
| knowledge-base | 8004 | Neo4j + JSON fallback 双后端存储 |
| refactoring-agent | 8005 | 架构坏味检测 + 重构模式推荐 |
| neo4j | 7474/7687 | 知识图谱数据库 |
| frontend | 3000 | 11 区结果展示 (对比矩阵/拓扑图/追踪/证据/组合/重构/ADR) |

## 快速启动

```bash
# 1. 配置 LLM (可选, 不配置则纯规则模式运行)
cp .env.example .env
# 编辑 .env 填入 LLM_API_BASE / LLM_API_KEY / LLM_MODEL

# 2. 启动全部服务
docker compose up --build

# 3. 初始化 Neo4j 知识图谱 (首次)
docker compose exec knowledge-base python init/init_neo4j.py

# 4. 打开前端
open http://localhost:3000
```

## LLM 配置

```bash
# .env 文件
LLM_API_BASE=https://api.deepseek.com/v1    # 兼容 OpenAI 协议
LLM_API_KEY=sk-xxxx
LLM_MODEL=deepseek-chat
```

LLM 不配置时系统自动降级为纯规则模式, 核心推荐链路不受影响。

## Neo4j 配置

```bash
# .env 文件 (默认)
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jneo4j
KNOWLEDGE_BACKEND=auto    # json / neo4j / auto
```

`auto` 模式优先 Neo4j, 不可用时自动 fallback JSON。JSON 模式零外部依赖。

## 演示输入

推荐在答辩时依次使用以下 4 个输入, 展示系统不同能力：

1. **基础推荐**: "开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话。"
   → Event-Driven Architecture

2. **组合推荐**: "构建电商平台，订单支付库存需要强一致事务，双十一高峰要抗压，多团队并行开发。"
   → Microservices + Event-Driven 组合

3. **重构建议**: "已有单体电商系统，订单库存耦合严重，性能瓶颈明显，希望拆分为微服务。"
   → 触发重构检测, 推荐绞杀者模式

4. **图谱证据**: "日志分析平台，每秒采集百万条日志并实时告警。"
   → 图谱质量属性匹配 + Pipeline-Filter 组合

## 技术建议覆盖

| 建议 | 状态 | 证据 |
|------|------|------|
| LLM + 知识图谱双驱动 | ✅ | graph_matcher.py + evaluation-agent |
| LangChain/LangGraph | ✅ | langchain_workflow.py (StateGraph) |
| Neo4j 图谱存储 | ✅ | graph_repository.py + JSON fallback |
| Few-shot Prompt | ✅ | requirements_few_shot.py (6) + evaluation_few_shot.py (3) |
| 规则引擎校验 | ✅ | score_style() 7 条规则 + 学习权重 |
| LLM 缓存 | ✅ | 内存/SQLite 双后端, /cache/stats |
| ADR 决策溯源 | ✅ | adr_records.json + /adr API |
| 组合推荐 | ✅ | combo_matcher.py + 5 种组合模式 |
| 重构建议 | ✅ | refactoring-agent + 5 种重构模式 |

## API 端点

| 服务 | 端点 | 说明 |
|------|------|------|
| api-gateway | POST /api/v1/recommend | 主推荐接口 |
| api-gateway | GET /cache/stats | 缓存统计 |
| api-gateway | POST /cache/clear | 清空缓存 |
| knowledge-base | GET /styles | 架构风格列表 |
| knowledge-base | GET /combinations | 组合模式列表 |
| knowledge-base | GET /graph/status | 图数据库状态 |
| knowledge-base | POST /graph/match | 图谱匹配 |
| knowledge-base | POST /adr | 保存 ADR |
| knowledge-base | GET /adr | ADR 列表 |
| knowledge-base | GET /adr/{id} | ADR 详情 |
| refactoring-agent | POST /refactor | 重构分析 |

## 测试

```bash
# 单元测试 (76 条)
pytest tests/unit/ -v

# 回归测试 (需要服务运行)
python tests/run_regression.py --gateway-url http://localhost:8000/api/v1/recommend

# 冒烟测试 (需要服务运行)
python tests/run_smoke.py

# 自动验收检查 (43 项)
python scripts/check_assignment.py --project-root .
```

## 目录结构

```
architecture-assistant/
├── docker-compose.yml
├── services/
│   ├── common/           # prompts/ + cache/
│   ├── api-gateway/      # LangGraph 编排 + 缓存
│   ├── requirements-agent/
│   ├── matching-agent/   # 规则 + 图谱 + 组合
│   ├── evaluation-agent/ # LLM 投票/摘要 + ADR
│   ├── knowledge-base/   # Neo4j + JSON
│   └── refactoring-agent/
├── frontend/
├── tests/
│   ├── unit/             # 6 个测试模块
│   └── datasets/         # 20 条需求用例
├── docs/                 # 需求/架构/测试/ADR/答辩
└── scripts/              # check_assignment.py
```
