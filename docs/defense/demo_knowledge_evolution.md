# 知识进化闭环 — 答辩演示脚本

> 用时：90 秒 | 方式：终端 curl 命令 | 准备：服务已启动，两个终端窗口

---

## 演示前准备（不纳入计时）

打开**两个终端窗口**并排显示：

| 终端 A（左下） | 终端 B（右下） |
|---------------|---------------|
| 用于发送 curl 命令 | 用于展示文件变化 |
| `cd architecture-assistant` | `cd architecture-assistant` |
| — | `docker exec knowledge-base sh -c "cat /app/data/learned_weights.json"` |

---

## 演示正文（90 秒）

### Step 1 — 首次推荐，展示初始得分（20 秒）

**终端 A**，执行：

```bash
curl -s -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{"requirement":"多团队协作开发SaaS平台，需要模块独立发布。"}' | python -m json.tool
```

**讲解词**：
> "我输入一条多团队协作的需求，系统推荐了微服务架构，得分 4 分。现在没有任何学习权重——这是纯规则引擎的结果。"

**盯住输出中的**：
```json
"candidates": [
  {"style": "Microservices", "score": 4, ...}
]
```

---

### Step 2 — 提交 3 条正向反馈，模拟用户修正（20 秒）

**终端 A**，连续执行 3 次：

```bash
curl -s -X POST http://localhost:8004/feedback \
  -H "Content-Type: application/json" \
  -d '{"requirement":"多团队协作开发SaaS平台，需要模块独立发布。","recommended_style":"Microservices","user_choice":"Microservices","comment":"多团队并行开发场景确认选微服务"}' | python -m json.tool
```

> 按 ↑ 键重复执行，共 3 次。

**讲解词**：
> "我模拟三位架构师对这条推荐给出了确认反馈。每次反馈提交后，系统从需求文本中提取特征维度——这里触发了 team_size_large（多团队协作）——然后更新该特征与微服务风格的关联计数。"

---

### Step 3 — 展示学习权重变化（20 秒）

**终端 B**，执行：

```bash
docker exec knowledge-base sh -c "cat /app/data/learned_weights.json"
```

**讲解词**：
> "注意看，team_size_large 维度下，Microservices 的计数从 0 变成了 3。这是 3 次确认反馈的累积效果。阈值设为 2 次——少于 2 次确认的不会生效，防止单次误操作污染知识库。"

**盯住输出**：
```json
{
  "team_size_large": {
    "Microservices": 3
  }
}
```

---

### Step 4 — 再次推荐，展示得分提升（20 秒）

**终端 A**，先清缓存再推荐：

```bash
curl -s -X POST http://localhost:8000/cache/clear
```

```bash
curl -s -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{"requirement":"多团队协作开发SaaS平台，需要模块独立发布。"}' | python -m json.tool
```

**讲解词**：
> "再次提交同一条需求，Microservices 的得分从 4 分提升到了 9 分。注意 reasons 里新增了一行 'learned boost: team_size_large→Microservices (confirmed 3x)'。这就是知识进化的完整闭环：反馈收集 → 特征提取 → 权重更新 → 评分生效。"

**盯住输出**：
```json
"reasons": [
  "matches feature: team_size_large",
  "extra rule: multi-team delivery favors microservices",
  "learned boost: team_size_large->Microservices (confirmed 3x)"
]
```

---

### 收尾（10 秒）

**讲解词**：
> "这个闭环的四个环节——反馈收集、特征提取、权重更新、评分生效——全部自动完成。不需要手动触发任何调度任务。虽然当前算法是简单的计数累加，但框架支持平滑升级为贝叶斯权重或 TF-IDF 加权。"

---

## 备用方案：如果演示时间紧张

合并 Step 2 + Step 3，用一条命令展示：

```bash
# 连发 3 条反馈
for i in 1 2 3; do
  curl -s -X POST http://localhost:8004/feedback \
    -H "Content-Type: application/json" \
    -d '{"requirement":"多团队协作开发SaaS平台","recommended_style":"Microservices","user_choice":"Microservices","comment":"确认"}' > /dev/null
done
# 展示权重
docker exec knowledge-base sh -c "cat /app/data/learned_weights.json"
```

---

## 演示检查清单

- [ ] Docker 服务全部启动（`docker compose ps` 全部 Up）
- [ ] 两个终端窗口已打开并排
- [ ] 终端 B 已准备好 `docker exec` 命令
- [ ] 网络畅通（`curl localhost:8000/health` 返回 `200`）
- [ ] 提前执行过至少一次推荐（预热 LLM 连接）

---

## FAQ：评委常见追问

### Q1: 阈值为什么是 2？能不能动态调整？

**答**: 2 是防噪声的最低有效门槛——1 次反馈可能是误操作。1.0 版本选择固定阈值以保持评分逻辑简单可解释。改进方向：新特征用低阈值加速冷启动（β=1），高频特征用高阈值增加鲁棒性（β=log(n)），可参考 Thompson Sampling 自适应调整。

### Q2: 权重会不会无限增长？

**答**: 当前会。1.0 版本采用简单累加，同一特征-风格关联被反复确认会线性增长。改进方向：EWMA（指数加权移动平均）`W_new = α·W_old + (1-α)·C_new`，或对数衰减 `W = log(1 + n)`。

### Q3: Neo4j 不可用时权重怎么算？

**答**: `_repo()` 调度器自动 fallback 到 JsonRepository——读 `feedback_log.json` + `learned_weights.json`。纯规则评分不受影响，仅 Neo4j 特有数据丢失。`GET /feedback/weights` 返回空权重时，`score_style()` 退化为纯规则+图谱评分。

### Q4: 用户反复确认错误推荐怎么办？

**答**: 当前无用户认证机制——所有反馈同等对待。改进方向：① 引入用户权重（领域专家 > 普通用户）；② 异常反馈检测（一条反馈同时确认所有维度可能是噪声）；③ 反馈时效衰减（旧反馈权重随时间递减）。

### Q5: 为什么反馈不带入"是哪个领域的"这个信息？

**答**: 这是有意设计的——权重按**特征维度**收敛。高并发→事件驱动的经验适用于所有领域（IM、支付、直播），不应该按领域隔离。如果按领域分桶学习，每个桶的样本量会被稀释，反而学不到通用原则。