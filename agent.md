# 软件体系结构大作业 — 全面检查报告

> 审计时间：2026-05-15
> 项目路径：`architecture-assistant/`

---

## 一、仓库结构总览

```
D:\桌面\大作业\软件体系\
├── architecture-assistant/           ★ 主项目（本报告审计对象）
│   ├── docker-compose.yml           (8 容器编排)
│   ├── README.md                    (完整启动文档)
│   ├── .env.example                 (LLM 配置模板)
│   ├── frontend/                    (Nginx + HTML/CSS/JS)
│   ├── services/
│   │   ├── common/
│   │   │   ├── cache/               (内存/SQLite 双缓存后端)
│   │   │   └── prompts/             (Few-shot prompt 库: 6+3 个示例)
│   │   ├── api_gateway/             (LangGraph 编排 + 手动 fallback, 端口8000)
│   │   ├── requirements_agent/      (10 维关键词词典 + LLM 语义补全, 端口8001)
│   │   ├── matching_agent/          (规则引擎 + Neo4j 图谱融合 + 组合推荐, 端口8002)
│   │   ├── evaluation_agent/        (LLM 投票 + LLM 摘要 + ADR 自动生成, 端口8003)
│   │   ├── knowledge_base/          (Neo4j + JSON 双后端存储, 端口8004)
│   │   └── refactoring_agent/       (5 种架构坏味 + 5 种重构模式, 端口8005)
│   ├── tests/
│   │   ├── unit/                    (6 个测试模块, ~80 条测试)
│   │   ├── datasets/                (20 条典型需求用例)
│   │   ├── run_regression.py        (回归测试运行器)
│   │   ├── run_smoke.py             (冒烟测试运行器)
│   │   └── generate_test_report.py  (测试报告生成器)
│   ├── docs/                        (7 份核心文档 + 答辩材料 + 复盘材料)
│   ├── scripts/
│   │   ├── check_assignment.py      (43 项自动验收检查)
│   │   └── generate_ppt.py          (621 行 Python PPTX 生成器)
│   └── interview/                   (面试准备 7 问)
├── SA/                              (课程参考资料)
├── .github/                         (GitHub agent 配置)
├── requierment.md                   (作业要求 Markdown 版)
├── 软件体系结构大作业要求.docx/pdf   (原始作业要求)
└── 实验报告模版.docx
```

---

## 二、逐项对照作业要求

### 核心功能（4/4）

| # | 要求 | 状态 | 实现位置 | 说明 |
|---|------|------|----------|------|
| 1 | **需求分析**：自然语言输入→语义理解→特征提取 | ✅ 已完成 | `requirements_agent/app/main.py:150-271` | 10 维关键词词典 + 否定语义过滤 + LLM 语义补全（规则命中≤2时触发）+ Few-shot prompt |
| 2 | **架构推荐**：≥3 种候选（含分层/微服务/事件驱动） | ✅ 已完成 | `matching_agent/app/main.py:103-169` | Top3 强制逻辑 + `MAINSTREAM_STYLES` 白名单确保覆盖三大主流 |
| 3 | **决策支持**：多维对比 + 最终推荐 + 优缺点评估报告 | ✅ 已完成 | `evaluation_agent/app/main.py:271-392` | `comparison_matrix` + `risk_and_suggestions` + `decision_basis`（rule + LLM） |
| 4 | **知识进化（进阶）**：知识库扩展 + 案例学习 | ✅ 已完成 | `knowledge_base/app/main.py:129-154`+`json_repository.py` | POST /feedback → 即时更新 learned_weights.json → 下次 match() 自动读取加分，完整事件驱动闭环，无需定时调度 |

### 技术要求（7/7）

| # | 要求 | 状态 | 实现细节 |
|---|------|------|----------|
| 1 | 微服务架构 | ✅ | docker-compose.yml: 8 容器独立部署，HTTP 互通 |
| 2 | ≥3 类智能体 | ✅ | 4 类：requirements-agent / matching-agent / evaluation-agent / refactoring-agent |
| 3 | 集成大语言模型 | ✅ | OpenAI 兼容协议，支持 DeepSeek / 通义千问，含超时(15-30s) + 降级 + fallback |
| 4 | 需求理解模块（非结构化特征提取） | ✅ | 并发/实时/可靠性/扩展性/复杂业务/强一致/部署约束/数据密集/多团队/安全 |
| 5 | 知识库模块（≥10 种架构风格） | ✅ | 10 种：分层/微服务/事件驱动/SOA/六边形/管道-过滤器/CQRS/Serverless/空间架构/CS |
| 6 | 推理决策模块（规则引擎 + LLM 混合） | ✅ | 规则引擎主导评分 + LLM 投票 tie-break + LLM 摘要生成 |
| 7 | 可视化模块（对比矩阵 + 拓扑图） | ✅ | Mermaid.js 渲染，10/10 风格均有 `topology_mermaid` 专属图 |

### 交付要求（11/11）

| # | 要求 | 状态 | 位置 |
|---|------|------|------|
| 1 | 需求规格说明书（含 AI 特有需求） | ✅ | `docs/01-需求规格说明书.md` |
| 2 | 架构设计文档（微服务/Agent/LLM 集成） | ✅ | `docs/02-架构设计文档.md` |
| 3 | 系统测试报告（含典型场景案例） | ✅ | `docs/03-系统测试报告.md` |
| 4 | 可运行演示系统（Web API） | ✅ | POST /api/v1/recommend + Swagger UI |
| 5 | 核心代码（Agent 协作 + LLM 调用） | ✅ | 全量 Python 源码 |
| 6 | 测试数据集（≥20 场景） | ✅ | `tests/datasets/requirements_cases.json` — 20 条，覆盖 10+ 领域 |
| 7 | 5 分钟系统演示讲稿 | ✅ | `docs/defense/01-5分钟系统演示讲稿.md` |
| 8 | 15 分钟架构设计专题讲稿 | ✅ | `docs/defense/02-15分钟架构设计专题讲稿.md` |
| 9 | 5 分钟问答准备 | ✅ | `docs/defense/03-5分钟问答准备.md` |
| 10 | C4 模型 / UML 图 | ✅ | `docs/defense/05-C4模型与UML图.md` |
| 11 | 答辩 PPT | ✅ | `scripts/generate_ppt.py`（621 行 Python PPTX 生成器） |

### 技术建议覆盖

| 建议 | 状态 | 证据 |
|------|------|------|
| LLM + 知识图谱双驱动 | ✅ | `graph_matcher.py` + `graph_repository.py`（Neo4j 404行 Cypher） |
| LangChain / LangGraph 框架 | ✅ | `langchain_workflow.py`（StateGraph: extract→match→evaluate→trace） |
| Neo4j 知识图谱存储 | ✅ | `graph_repository.py` + JSON fallback `KNOWLEDGE_BACKEND=auto` |
| Few-shot Prompt Engineering | ✅ | requirements 6 例（模糊/否定/安全/数据/一致/重构）+ evaluation 3 例 |
| 规则引擎结果校验 | ✅ | `score_style()`: 7 条领域规则 + 学习权重累计 |
| LLM 结果缓存机制 | ✅ | 内存 / SQLite 双后端 + 请求级 SHA-256 缓存 + `/cache/stats` |
| **ADR 决策溯源**（创新①） | ✅ | evaluation-agent 自动生成 ADR → knowledge-base 持久化 → 查询 |
| **组合架构推荐**（创新②） | ✅ | `combo_matcher.py` + 5 种组合模式（微服务+事件驱动 / 分层+CQRS / 管道-过滤器+事件驱动 等） |
| **架构重构建议**（创新③） | ✅ | `refactoring_agent`: 5 种坏味（单体耦合/扩展瓶颈/发布周期长/遗留系统/数据耦合）+ 5 种重构模式（绞杀者/防腐层/模块化单体/CQRS/事件驱动迁移） |

---

## 三、代码质量评估

### 智能体协作逻辑 ⭐⭐⭐⭐⭐

| 层面 | 评价 |
|------|------|
| 编排架构 | `api_gateway/app/main.py:88-140`：LangGraph（主） + 手动串行（fallback）双引擎，拓扑清晰 |
| LangGraph 节点 | `langchain_workflow.py:152-165`：4节点线性 StateGraph（extract→match→evaluate→trace） |
| 非阻塞设计 | `main.py:194-211`：重构建议失败不阻塞主推荐链路 |
| 错误追踪 | 每个节点记录 `elapsed_ms` + `status` + `error` 到 `trace` 数组 |
| Agent 职责 | 各 Agent 单一职责：提取 / 匹配 / 评估 / 重构，独立部署独立扩展 |

### LLM 调用实现 ⭐⭐⭐⭐⭐

| 策略 | 实现 |
|------|------|
| 降级链 | LLM 未配置 → 纯规则模式；LLM 超时 → fallback 摘要；LLM JSON解析失败 → 清洗后重试 |
| 并发优化 | `evaluation_agent/app/main.py:280-283`：LLM 投票与摘要通过 `asyncio.gather` 并行 |
| Few-shot | `requirements_few_shot.py`: 6例覆盖全部边界场景；`evaluation_few_shot.py`: 3例覆盖主流风格 |
| 协议兼容 | 标准 OpenAI `/chat/completions`，切换模型仅需改 `.env` 中三个变量 |

### 异常处理 ⭐⭐⭐⭐

| 场景 | 处理方式 |
|------|----------|
| LLM 不可用 / 超时 | `try/except → None/false → 规则降级` |
| Neo4j 不可用 | `_repo()` 调度器返回 None → JSON fallback |
| 知识库 HTTP 不可用 | matching-agent 捕获 `httpx.HTTPError` → 502 |
| 重构 Agent 不可用 | 日志 WARNING，不阻塞推荐 |
| ADR 生成失败 | 日志 WARNING，report 中 `adr_status=failed` |
| JSON 解析异常 | Markdown 代码块剥离 + `json.loads` try/except |

**改进建议**：缺少熔断器，多次连续超时无断路器状态；各 Agent 间无重试+退避策略

---

## 四、单元测试覆盖详细分析

### 6 个测试文件与测试数

| 文件 | 测试数 | 覆盖的核心函数 |
|------|--------|----------------|
| `tests/unit/test_requirements.py` | 8 | keyword_hits / filter_negation / extract / few-shot prompts |
| `tests/unit/test_evaluation.py` | ~18 | score_style(验证) / _localize_reasons / _dynamic_risks / evaluate(mock) / few-shot |
| `tests/unit/test_matching.py` | 9 | score_style / blend_scores(3种) / score_combination / rank_combinations |
| `tests/unit/test_knowledge.py` | 22(3条件) | JSON存储 / 扩展 / feedback / JsonRepository / Neo4j / ADR |
| `tests/unit/test_gateway.py` | 13 | WorkflowState / build_workflow / RecommendResponse / cache工具 |
| `tests/unit/test_refactoring.py` | 10 | detect_smells / select_patterns / build_rule_template |
| **合计** | **~80** | |

### 已覆盖 vs 未覆盖的核心路径

```
已覆盖 ✅
├── requirements_agent: keyword_hits / filter_negation / extract 完整流程
├── matching_agent:     score_style(tag+规则) / blend_scores(3分支) / combo评分排序
├── evaluation_agent:   _localize_reasons / _dynamic_risks / evaluate(mock) / few-shot prompts
├── refactoring_agent:  detect_smells(3场景) / select_patterns(2场景) / build_rule_template(5场景)
├── knowledge_base:     JSON存储CRUD / feedback / ADR完整生命周期 / JsonRepository方法
├── api_gateway:        workflow_state模型 / build_workflow(None分支) / RecommendResponse模型
├── common/cache:       get/set/clear/stats/disabled/expired/knowledge_version
└── common/prompts:     few-shot prompts数量+内容+结构完整性

未覆盖 ❌（标★为核心高风险项）
├── api_gateway ★★★★★
│   ├── _manual_orchestrate() — 三步串行编排
│   ├── _langgraph_orchestrate() — LangGraph编排
│   └── recommend() — cache hit/miss/fallback全路径
├── evaluation_agent ★★★★
│   ├── llm_summary() 的 fallback 到 _fallback_summary 路径
│   ├── _fallback_summary() 格式化输出
│   └── llm_vote_style() 异常/超时路径
├── matching_agent ★★★
│   ├── learned_weights 累计加分路径
│   └── top3 补齐逻辑边界（全零分/非主流补位等）
├── knowledge_base ★★★
│   ├── _repo() 调度器逻辑（BACKEND=json/neo4j/auto 三种）
│   └── 所有 FastAPI 端点（TestClient）
├── refactoring_agent ★★
│   ├── llm_polish() 润色路径
│   └── refactor() 端点完整流程
└── requirements_agent ★★
    └── llm_semantic_supplement() LLM补全流程
```

### 各模块覆盖率估算

```
requirements_agent/     ████████░░  80%  (lexicon逻辑全测, LLM补全未测)
matching_agent/         ██████░░░░  60%  (核心规则测了, learn_weights+top3边界+fetch未测)
evaluation_agent/       █████░░░░░  50%  (工具函数全测, fallback+LLM异常未独立测)
knowledge_base/         ████████░░  80%  (JSON存储全测, 端点+_repo调度未测)
refactoring_agent/      ████████░░  80%  (规则逻辑全测, LLM+端点未测)
api_gateway/            ██░░░░░░░░  20%  (仅模型+缓存工具, 编排核心未测)
common/cache/           █████████░  90%  (基本全覆盖)
common/prompts/         █████████░  90%  (基本全覆盖)
```

---

## 五、缺口清单

### ⚠️ 部分完成（2项）

| # | 项目 | 当前实现 | 缺失部分 | 影响权重 |
|---|------|----------|----------|----------|
| 1 | **单元测试边界覆盖** | ~80 条测试覆盖核心规则逻辑 | api_gateway编排(20%)、evaluation fallback(50%)、matching边界(60%) 覆盖不足 | 测试验证10% |
| 2 | **真实 LLM 联调验证** | 代码逻辑完备，支持所有降级路径 | 需用真实 API Key 验证 Few-shot 效果 + LLM 投票准确性 | 系统实现5% |

### ❌ 未完成（0项）

无致命缺失。所有作业要求均有对应实现。

---

## 六、优先级建议（按评分权重排序）

| 优先级 | 任务 | 内容简述 | 预估工时 | 预期提分 |
|--------|------|----------|----------|----------|
| **P0** | 配置真实 LLM API Key 运行全流程 | `.env` 已配置，启动服务运行回归测试验证端到端效果 | 1h | +3分 |
| **P1** | 补充编排层单元测试（3条路径） | recommend(): cache hit / langgraph / fallback | 1h | +2分 |
| **P2** | 补充 matching/evaluation 边界测试 | learned_weights / top3补齐 / _fallback_summary / llm_vote异常 | 2h | +2分 |
| **P3** | TestClient 端点测试 | knowledge-base / refactoring-agent 端点覆盖 | 1h | +1分 |

---

## 七、评分预估

| 考核维度 | 权重 | 得分 | 得分率 | 主要扣分项 |
|----------|------|------|--------|-----------|
| **需求分析** | 15% | **14/15** | 93% | 无不确定性处理显式策略说明(-1) |
| **架构设计** | 30% | **28/30** | 93% | Agent间通信可引入消息队列增强(-1)、知识进化算法加权策略简化(-1) |
| **系统实现** | 25% | **23/25** | 92% | 单元测试覆盖不均(-1)、缺少熔断器(-1) |
| **测试验证** | 15% | **12/15** | 80% | 核心编排层未测(-2)、边界分支遗漏(-1) |
| **答辩表现** | 15% | **13/15** | 87% | 材料充分但依赖临场(-2) |
| **总分** | **100%** | **≈90/100** | **90%** | 知识进化闭环完整、全部技术建议已实现、三个创新方向全覆盖 |

---

## 八、技术亮点总结

1. **混合推理机制**：规则引擎(score_style 7条规则+学习权重) + LLM 投票(tie-break +1) + LLM 摘要
2. **智能降级**：4级降级链（LangGraph→手动编排→规则引擎→模板回退），任一层失败不影响最终输出
3. **双后端存储**：knowledge-base `_repo()` 调度器统一接口，Neo4j/JSON 零切换成本
4. **完整的 DevOps**：docker-compose 一键启动 + 43项自动化验收 + 回归/冒烟/单元三层测试
5. **三个创新方向全覆盖**：ADR 决策溯源 / 组合架构推荐 / 架构重构建议

---

## 九、参考信息

### 关键文件索引

| 用途 | 文件路径 | 行数 |
|------|----------|------|
| 入口编排 | `services/api_gateway/app/main.py` | 236 |
| LangGraph 工作流 | `services/api_gateway/app/langchain_workflow.py` | 168 |
| 需求特征提取 | `services/requirements_agent/app/main.py` | 271 |
| 规则引擎评分 | `services/matching_agent/app/main.py` | 169 |
| 图谱融合 | `services/matching_agent/app/graph_matcher.py` | 93 |
| 组合推荐 | `services/matching_agent/app/combo_matcher.py` | 113 |
| LLM 投票/摘要/ADR | `services/evaluation_agent/app/main.py` | 392 |
| Neo4j 图存储 | `services/knowledge_base/app/graph_repository.py` | 404 |
| JSON 存储 | `services/knowledge_base/app/json_repository.py` | 233 |
| 知识库调度 | `services/knowledge_base/app/main.py` | 227 |
| 重构建议 | `services/refactoring_agent/app/main.py` | 334 |
| 前端可视化 | `frontend/index.html` | 288 |
| 测试数据集 | `tests/datasets/requirements_cases.json` | 22条(20用例) |
| 需求 few-shot | `services/common/prompts/requirements_few_shot.py` | 86 |
| 评估 few-shot | `services/common/prompts/evaluation_few_shot.py` | — |
| 内存缓存 | `services/common/cache/simple_cache.py` | 95 |
| SQLite 缓存 | `services/common/cache/sqlite_cache.py` | 154 |
| 架构风格数据 | `services/knowledge_base/data/architecture_styles.json` | 341 |
| 组合模式数据 | `services/knowledge_base/data/architecture_combinations.json` | 64 |
| 自动验收脚本 | `scripts/check_assignment.py` | 1286 |

### 启动命令

```bash
# Docker 启动
docker compose up --build

# 初始化 Neo4j 知识图谱
docker compose exec knowledge-base python init/init_neo4j.py

# 访问前端
open http://localhost:3000

# 运行测试
pytest tests/unit/ -v
python tests/run_regression.py --gateway-url http://localhost:8000/api/v1/recommend
python scripts/check_assignment.py --project-root .
```

### 演示输入（推荐 4 个）

```
1. 基础推荐: "开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话。"
   → Event-Driven Architecture

2. 组合推荐: "构建电商平台，订单支付库存需要强一致事务，双十一高峰要抗压，多团队并行开发。"
   → Microservices + Event-Driven 组合

3. 重构建议: "已有单体电商系统，订单库存耦合严重，性能瓶颈明显，希望拆分为微服务。"
   → 触发重构检测，推荐绞杀者模式

4. 图谱证据: "日志分析平台，每秒采集百万条日志并实时告警。"
   → 图谱质量属性匹配 + Pipeline-Filter 组合
```
