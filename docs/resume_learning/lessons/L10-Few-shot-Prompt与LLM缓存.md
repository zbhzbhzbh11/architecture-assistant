# L10 · Few-shot Prompt 与 LLM 缓存

> "好的 Prompt 让 LLM 少犯错，好的缓存让 LLM 不用再犯同样的错。"

---

## 本节目标

学完本节，你将能够：

1. 说出 9 个 Few-shot 示例的场景覆盖
2. 解释为什么需求侧和评估侧的示例数量不同（6 vs 3）
3. 理解双后端缓存的选择逻辑和自动失效机制
4. 回答："你是怎么写这些 Prompt 的？调了几次？"

---

## 为什么需要 Few-shot Prompt

### 一个"填表说明"的类比

你去政府办事，工作人员给你一张表说"填一下"。你看着空白表格不知所措——写什么？格式是什么？多长？

这时候如果有一张**填好的样表**贴在旁边，你一看就懂了。Few-shot Prompt 就是这个"样表"——在 Prompt 前放几个范例，告诉 LLM "这就是我想要的输出格式和风格"。

### 为什么零样本不够

零样本 Prompt：
> "判断以下需求涉及哪些特征维度..."

问题：LLM 可能返回 `"高并发"`（中文标签），也可能返回 `high_concurrency`（英文 key），还可能返回一段解释性文字而不是纯 JSON。

Few-shot Prompt 通过示例**锁定了输出格式**——每个示例都是 `{"特征名": true/false}` 的严格 JSON，LLM 学会了"我只应该输出这个格式"。

---

## 当前项目如何实现

### 需求侧 Few-shot：6 个示例

来源文件：[common/prompts/requirements_few_shot.py](../services/common/prompts/requirements_few_shot.py)

| # | 示例需求 | 覆盖场景 |
|---|---------|---------|
| 1 | "日活百万，双11暴增" | **模糊高并发**（不含"并发"二字） |
| 2 | "后台管理系统，不需要实时处理" | **否定语义**（明确排除某维度） |
| 3 | "医疗数据平台，涉及患者隐私" | **安全合规**（含脱敏/审计/权限） |
| 4 | "每天采集TB级日志，ETL管道清洗" | **数据密集**（流处理/批处理） |
| 5 | "银行核心转账，每笔必须ACID一致提交" | **强一致性**（金融场景） |
| 6 | "现有单体电商性能瓶颈，拆分微服务" | **架构重构倾向**（团队+可扩展） |

**为什么是 6 个？** 因为需求分析场景多变——有的非常明确（示例 5），有的非常模糊（示例 1），有的含有否定（示例 2），有的涉及多维度（示例 6）。6 个示例覆盖了 10 个维度中每个维度的典型表述方式。

### 评估侧 Few-shot：3 个示例

来源文件：[common/prompts/evaluation_few_shot.py](../services/common/prompts/evaluation_few_shot.py)

| # | 核心推荐 | 价值 |
|---|---------|------|
| 1 | Event-Driven Architecture | 展示"高并发+实时"场景的报告风格 |
| 2 | Microservices | 展示"多团队+强一致"场景的报告风格 |
| 3 | Layered Architecture | 展示"复杂业务+稳定迭代"场景的报告风格 |

**为什么是 3 个？** 评估报告的格式是固定的四段式：推荐→理由→优劣→风险。3 个示例分别覆盖三种最常推荐的核心风格——每种风格的用语、风险描述、建议都是不同的。更多示例会导致 Prompt 过长（token 浪费），3 个刚好覆盖核心场景。

### Few-shot 的降级设计

```python
# requirements_agent/app/main.py:98-104
try:
    from common.prompts.requirements_few_shot import build_few_shot_prompt
    prompt = build_few_shot_prompt(text)
except ImportError:
    # 模块不可用时自动降级为零样本 Prompt
    prompt = (
        "分析以下软件需求描述, 判断是否涉及这些特征维度: "
        f"{zh_labels}。"
        "返回严格的 JSON 格式..."
    )
```

**如果 Few-shot 模块不存在**（比如部署时漏拷了文件），系统不会报错——自动降级为零样本 Prompt。虽然输出质量可能略降，但功能不断。

---

## 为什么需要 LLM 缓存

### 一个"复印机"的类比

你去打印店复印一份文件，老板说你稍等，然后花 5 分钟重新手抄了一份给你——而不是用复印机。

LLM 调用就是那个"手抄"——每次调用都要消耗 Token 和时间。如果同一个需求（或相似需求）反复问，每次都重新调 LLM 是巨大的浪费。

缓存就是"复印机"——问过的需求，下次直接返回保存的结果。

---

## 缓存系统实现

### 双后端设计

| 后端 | 适用场景 | 持久化 |
|------|---------|--------|
| **内存缓存** (simple_cache.py) | 默认方案，零配置 | 否，重启丢失 |
| **SQLite 缓存** (sqlite_cache.py) | 需要跨重启保留 | 是，存文件 |

**选择方式**：环境变量 `CACHE_BACKEND=memory` 或 `sqlite`。

两个后端实现**完全相同的接口**（`get/set/clear/stats`），api-gateway 在启动时根据环境变量选择：

```python
# api_gateway/app/main.py:22-26
if CACHE_BACKEND == "sqlite":
    from common.cache.sqlite_cache import get as cache_get, set as cache_set, ...
else:
    from common.cache.simple_cache import get as cache_get, set as cache_set, ...
```

### 缓存键生成

```python
# common/cache/hash_utils.py:29-36
def cache_key(requirement, model="", prefix="req"):
    kv = knowledge_version()  # styles 文件 MD5 前 8 位
    raw = f"{prefix}|{requirement}|{model}|{kv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

**缓存键包含四个要素**：
1. **requirement**：相同需求 → 相同结果
2. **model**：换了 LLM 模型 → 不共享缓存
3. **knowledge_version**：知识库更新 → 旧缓存自动失效
4. **prefix**：不同类型缓存（请求级 / prompt级 / 评估级）的命名空间隔离

### 自动失效机制

```python
# common/cache/hash_utils.py:10-22
def _get_knowledge_version():
    env_version = os.getenv("KNOWLEDGE_VERSION", "").strip()
    if env_version:
        return env_version
    # 默认：architecture_styles.json 的 MD5 前 8 位
    styles_path = ... / "architecture_styles.json"
    return hashlib.md5(f.read()).hexdigest()[:8]
```

**只要你改了 `architecture_styles.json`（新增/修改/删除一个架构风格），所有旧缓存自动失效。** 不需要手动清缓存。

### 缓存管理 API

| 端点 | 返回示例 |
|------|---------|
| `GET /cache/stats` | `{"backend": "sqlite", "entries": 12, "hits": 34, "misses": 20, "hit_rate": 0.63}` |
| `POST /cache/clear` | `{"status": "ok", "cleared": 12}` |

前端可以展示缓存命中率，在答辩时作为"系统性能优化"的亮点。

---

## 核心代码路径

| 文件 | 关键内容 |
|------|---------|
| [common/prompts/requirements_few_shot.py](../services/common/prompts/requirements_few_shot.py) | 6 个需求 Few-shot 示例 |
| [common/prompts/evaluation_few_shot.py](../services/common/prompts/evaluation_few_shot.py) | 3 个评估 Few-shot 示例 |
| [common/cache/simple_cache.py](../services/common/cache/simple_cache.py) | 内存缓存（TTL + 线程安全） |
| [common/cache/sqlite_cache.py](../services/common/cache/sqlite_cache.py) | SQLite 持久化缓存 |
| [common/cache/hash_utils.py](../services/common/cache/hash_utils.py) | 缓存键生成 + knowledge_version |
| [requirements_agent/app/main.py:98-104](../services/requirements_agent/app/main.py#L98-L104) | Few-shot 降级 |
| [evaluation_agent/app/main.py:69-75](../services/evaluation_agent/app/main.py#L69-L75) | 评估侧 Few-shot 降级 |
| [api_gateway/app/main.py:166-178](../services/api_gateway/app/main.py#L166-L178) | 缓存读取逻辑 |

---

## 面试官可能怎么问

**Q1: Few-shot 示例是怎么设计的？调了多久？**

> 设计的核心原则是"场景覆盖而非数量堆积"。需求侧 6 个示例覆盖了：模糊描述、否定语义、安全合规、数据密集、强一致、重构倾向——这是 10 个维度中最需要 LLM 帮助的典型场景。评估侧 3 个示例分别对应三种最常推荐的核心风格。每个示例的输入输出我都跑了多次验证，确保 LLM 在见过这 6+3 个样本后，对 20 条回归用例的输出一致性显著提升。

**Q2: 如果 Few-shot 模块文件被误删了，系统会怎样？**

> 不会 crash。两个 Agent 在 `import` Few-shot 模块时都有 `try/except ImportError`——如果模块不可用，自动降级为零样本 Prompt。虽然输出质量可能略降（格式化程度降低、语言风格不如 few-shot 一致），但核心功能完全不受影响。

**Q3: SQLite 缓存和内存缓存你推荐哪个？**

> 看场景。演示/答辩用内存缓存就够了——反正每次答辩都是新请求，不需要跨重启保留。但如果系统长期运行（比如作为一个内部工具），SQLite 缓存可以积累历史请求的缓存，命中率高得多。我的默认配置是内存缓存——因为这是"最不需要依赖"的选项。

**Q4: 缓存会不会返回过期结果？**

> 不会。缓存键里包含 `knowledge_version`——它是 `architecture_styles.json` 文件内容的 MD5 前 8 位。一旦你修改了知识库（比如新增一种风格），`knowledge_version` 自动改变，所有旧缓存立刻失效。不需要手动清。

---

## 简历上如何表达

> 设计 9 个中文 Few-shot Prompt 示例（需求 6 + 评估 3），覆盖模糊语义、否定过滤、安全合规等典型场景；Few-shot 模块不可用时自动降级为零样本；实现内存/SQLite 双后端请求缓存，SHA256 缓存键 + knowledge_version 自动失效机制。

---

## 本节小结

| 要点 | 一句话 |
|------|--------|
| Few-shot 示例数 | 需求侧 6 个（场景覆盖），评估侧 3 个（风格覆盖） |
| Few-shot 降级 | ImportError → 零样本 Prompt |
| 双后端缓存 | 内存（默认，零配置）+ SQLite（持久化，跨重启） |
| 缓存键要素 | requirement + model + knowledge_version + prefix |
| 自动失效 | knowledge_version = styles 文件 MD5，改了知识库就失效 |
| 可观测 | /cache/stats 暴露命中率，演示时可展示 |
