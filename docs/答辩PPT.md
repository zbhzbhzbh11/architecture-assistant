---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    background: white;
    color: #1E293B;
  }
  section.cover {
    background: linear-gradient(135deg, #0F172A, #1E3A5F);
    color: white;
  }
  section.cover h1 {
    font-size: 2.4em;
    margin-bottom: 0.3em;
  }
  section.cover p {
    font-size: 1.1em;
    color: #93C5FD;
    line-height: 1.8;
  }
  h1 {
    color: #1E40AF;
    border-bottom: 3px solid #3B82F6;
    padding-bottom: 0.3em;
  }
  h2 {
    color: #1E3A5F;
  }
  ul li {
    margin: 0.4em 0;
    line-height: 1.6;
  }
  ul li ul li {
    font-size: 0.9em;
    color: #475569;
  }
  .note {
    font-size: 0.7em;
    color: #9CA3AF;
    position: fixed;
    bottom: 30px;
    left: 60px;
  }
  .highlight {
    background: #DBEAFE;
    padding: 0.15em 0.4em;
    border-radius: 4px;
    font-weight: bold;
  }
  .badge-green {
    background: #D1FAE5;
    color: #065F46;
    padding: 0.1em 0.5em;
    border-radius: 10px;
    font-size: 0.85em;
  }
  .badge-red {
    background: #FEE2E2;
    color: #991B1B;
    padding: 0.1em 0.5em;
    border-radius: 10px;
    font-size: 0.85em;
  }
  table {
    font-size: 0.8em;
  }
  th {
    background: #1E40AF;
    color: white;
  }
---

<!-- _class: cover -->

# 基于大模型的<br/>软件架构风格智能助手

软件体系结构课程大作业

2026年X月

<br/>

将 **自然语言需求** → **可解释的架构推荐**

---

## 作业目标与核心功能

| 能力 | 说明 |
|---|---|
| **需求分析** | 接收自然语言需求，提取 10 维度关键特征（高并发/实时性/安全性/可扩展性...） |
| **架构推荐** | 推荐 ≥3 种候选架构风格，含分层/微服务/事件驱动等主流架构 |
| **决策支持** | 多维度对比矩阵 + 最终推荐 + 优缺点分析 + 风险评估 |
| **知识进化** | 可扩展知识库（10 种风格）+ 案例反馈学习机制 |

<div class="note">四大核心能力闭环：输入自然语言 → 输出可解释的架构推荐</div>

---

## 系统总体架构

```
用户（浏览器 / API）
        │
        ▼
┌───────────────────────────────┐
│   架构风格智能助手（6 容器）     │
│  Frontend :3000                │
│  API Gateway :8000             │
│  Requirements Agent :8001      │
│  Matching Agent :8002          │
│  Evaluation Agent :8003        │
│  Knowledge Base :8004          │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│   LLM 服务（DeepSeek v4-flash）│
│   OpenAI 兼容协议，可替换       │
└───────────────────────────────┘
```

<div class="note">LLM 是外部依赖而非系统内核，支持一键切换</div>

---

## 微服务划分（5+1）

| 服务 | 端口 | 职责 | 关键技术 |
|---|---|---|---|
| **api-gateway** | 8000 | 统一入口，编排调用 | FastAPI, httpx |
| **requirements-agent** | 8001 | 特征提取 + LLM 补全 | 10 维词典, 否定过滤 |
| **matching-agent** | 8002 | 规则评分 + Top3 | 标签匹配, 专家规则 |
| **evaluation-agent** | 8003 | LLM 推理 + 报告 | DeepSeek, 混合推理 |
| **knowledge-base** | 8004 | 风格数据 + 反馈 | JSON, 可扩展 |
| **frontend** | 3000 | 可视化展示 | HTML, Mermaid.js |

**划分理由：** 异构成分隔离（规则 vs LLM）· 故障隔离 · 独立演进

---

## Agent 协作机制

```
Gateway
  │ POST /extract
  ├──► Requirements Agent ──► {features, feature_hits}
  │
  │ POST /match
  ├──► Matching Agent ──► {candidates[Top3]}
  │     │ GET /styles
  │     └──► Knowledge Base
  │
  │ POST /evaluate
  └──► Evaluation Agent ──► {recommended_style, matrix, risks}
        │
        ├──► LLM (vote + summary)
        └──► 降级时规则独立运行
```

**Pipeline-Agent 模式：** 单一职责 · 数据驱动流转 · LLM 仅最后一环参与

---

## LLM 集成方案

**两套 Prompt 分工：**

| 功能 | t | 角色 | 输出 |
|---|---|---|---|
| `llm_vote_style` | 0.0 | strict judge | 仅风格名 |
| `llm_summary` | 0.3 | architecture reviewer | 结构化中文报告 |

**四层防护：**

1. ⏱ 20s 超时控制
2. 🛡 try-except 全量捕获
3. 📋 降级为规则引擎格式化摘要
4. ⏭ 未配置 Key 时自动跳过

<div class="note">LLM 完全不可用时，规则引擎独立运行，核心链路不中断</div>

---

## 架构知识库设计

**10 种架构风格 × 6 字段：**

```
Layered · Microservices · Event-Driven · SOA · Hexagonal
Pipeline-Filter · CQRS · Serverless · Space-Based · Client-Server
```

每条风格含：`name` `tags` `best_for` `pros` `cons` `topology_mermaid`

**扩展机制：**
- `POST /styles` → 动态新增风格
- `POST /feedback` → 案例反馈收集
- `GET /feedback/stats` → 准确率统计

<div class="note">JSON 存储，设计文档已说明 Neo4j 升级路径</div>

---

## 混合推理机制（核心创新）

<div style="display:flex;gap:40px">

<div style="flex:1;background:#EFF6FF;padding:16px;border-radius:8px">

### 规则引擎
**（确定性 · 保下限）**

✅ tags 匹配 +2/tag<br/>
✅ 额外专家规则 +1<br/>
✅ 主流白名单兜底<br/>
✅ 评分完全可追溯

</div>

<div style="flex:1;background:#FEF3C7;padding:16px;border-radius:8px">

### LLM 增强
**（语义性 · 提上限）**

✅ 投票 +1 tie-break<br/>
✅ 中文结构化分析<br/>
✅ 失败静默降级<br/>
✅ 不颠覆规则排序

</div>

</div>

<br/>

> **纯规则泛化弱 · 纯 LLM 不稳定 → 协同方案取其长**

---

## 架构推荐全链路

```
输入：自然语言需求
  │
  ▼
[Step 1] 需求理解
  ├─ 10 维度 × ~100 关键词匹配
  ├─ filter_negation() 否定过滤
  └─ 命中 ≤2 → LLM 语义补全 (t=0.1)
  │
  ▼
[Step 2] 架构匹配
  ├─ score_style() 逐风格评分
  ├─ 额外规则 + 主流白名单
  └─ Top3 候选精选
  │
  ▼
[Step 3] 混合评估
  ├─ 规则排序 + LLM 投票 (+1)
  └─ LLM 生成结构化中文报告
  │
  ▼
输出：核心推荐 + 备选 + 矩阵 + 风险 + 拓扑图
```

---

## 可视化：对比矩阵与拓扑图

**前端四区域：**

| 区域 | 内容 | 数据来源 |
|---|---|---|
| 🏷 推荐摘要 | 核心推荐 + 备选 + LLM 分析报告 | evaluation-agent |
| 📊 特征卡片 | 命中维度 + 关键词证据 | requirements-agent |
| 📋 对比矩阵 | 6 列：类型/风格/得分/理由/优点/缺点 | evaluation-agent |
| 🗺 拓扑图 | Mermaid.js 动态渲染 | knowledge-base JSON |

> 拓扑图不是静态图片 —— 10 种风格各有专属 Mermaid 定义，修改图只需改 JSON

---

## 系统演示（参考案例）

**输入：**
> 开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话

**输出：**

| 步骤 | 结果 |
|---|---|
| 特征提取 | <span class="badge-green">高并发</span> <span class="badge-green">实时性</span> <span class="badge-green">可靠性</span> <span class="badge-green">可扩展性</span> |
| 候选架构 | **Event-Driven(7分)** + Microservices(5分) + CQRS(4分) |
| LLM 报告 | 3 条推荐理由 + √3 优点 + ×3 缺点 + 风险建议 |
| 拓扑图 | Client→Gateway→Producer→EventBus→Consumers |

---

## 测试验证

**三层测试体系：**

| 层级 | 工具 | 用例 |
|---|---|---|
| 单元测试 | pytest | 核心算法 4 条 |
| 冒烟测试 | run_smoke.py | 20 条快速验证 |
| 回归测试 | run_regression.py | 20 条 + 5 指标统计 |

**回归测试结果（实测）：**

| 指标 | 结果 |
|---|---|
| 通过率 | **100%** (20/20) |
| Top3 完整率 | **100%** |
| 主流覆盖率 | **100%** |
| 推荐产出率 | **100%** |
| 可解释率 | **100%** |
| 平均时延 | ~10s |

<div class="note">python scripts/check_assignment.py → 21/21 全部通过</div>

---

## 异常处理与可靠性

| 层级 | 措施 |
|---|---|
| **网关层** | 统一 502/500 · `trust_env=False` 绕过代理 |
| **LLM 层** | 20s 超时 · try-except · 降级摘要 · 自动跳过 |
| **前端层** | 防重复提交 · 错误分支不崩溃 |

**容错性：**

- ✅ 单 Agent 故障不影响网关
- ✅ LLM 完全不可用 → 规则引擎独立输出完整推荐
- ✅ `.env` 自动加载，Key 不硬编码

---

## 项目创新点

1. **混合推理机制**
   规则保下限 + LLM 提上限 + 三层证据可追溯

2. **Pipeline-Agent 协作**
   职责单一体现在独立容器中，非单体内部模块划分

3. **数据驱动拓扑图**
   10 种风格 Mermaid 定义存于知识库，API 动态返回

4. **案例学习闭环**
   反馈收集 → 统计 → 可驱动自动权重更新

---

## 总结与展望

**当前成果：**

- ✅ 功能完整 — 需求→推荐→解释 闭环
- ✅ 测试充分 — 20/20 通过，全部指标 100%
- ✅ 工程完善 — 6 容器、日志、异常、降级
- ✅ 文档齐全 — 需求+架构+测试+答辩

**后续改进：**

- → 案例学习：反馈数据 → 自动权重更新
- → 知识库：JSON → Neo4j 图数据库
- → 性能：LLM 调用并行化（-40% 时延）

<br/>

# 谢谢各位老师！
