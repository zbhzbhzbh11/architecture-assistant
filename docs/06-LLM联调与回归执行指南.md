# LLM联调与回归执行指南（迭代-03）

## 目标
- 完成“至少一个大语言模型”真实接入验证。
- 对 20 条测试场景执行回归并产出量化结果。
- 为测试报告与答辩提供可追溯证据。

## 1. 环境准备
1. 复制环境变量模板：
- `.env.example` -> `.env`

2. 在 `.env` 中填写任一供应商配置（OpenAI兼容接口）：
- DeepSeek 示例：
  - `LLM_API_BASE=https://api.deepseek.com/v1`
  - `LLM_API_KEY=你的Key`
  - `LLM_MODEL=deepseek-chat`
- 通义千问兼容网关示例：
  - `LLM_API_BASE=你的OpenAI兼容网关地址`
  - `LLM_API_KEY=你的Key`
  - `LLM_MODEL=qwen-plus`

## 2. 启动系统（优先）
如果本机有 Docker：
1. 在项目根目录执行：
- `docker compose up --build`
2. 检查健康接口：
- `http://localhost:8000/health`
- `http://localhost:8001/health`
- `http://localhost:8002/health`
- `http://localhost:8003/health`
- `http://localhost:8004/health`

## 3. 执行回归测试
1. 安装测试依赖：
- `pip install -r tests/requirements.txt`

2. 执行回归脚本：
- `python tests/run_regression.py --gateway-url http://localhost:8000/api/v1/recommend`

3. 产物位置：
- `tests/results/regression_result.json`
- `tests/results/regression_summary.md`

4. 生成系统测试报告：
- `python tests/generate_test_report.py --result tests/results/regression_result.json --out docs/03-系统测试报告.md`

## 4. 验收门槛（建议）
- 通过率 >= 90%
- Top3 完整率 = 100%
- 主流架构覆盖率 = 100%
- 决策可解释率 >= 95%
- 平均响应时延（本机）可控并可复现

## 5. 证据归档清单（答辩必备）
1. `.env` 中模型配置（打码截图）。
2. 接口联调截图：`/api/v1/recommend` 请求与响应。
3. 回归结果文件：
- `tests/results/regression_result.json`
- `tests/results/regression_summary.md`
4. 自动生成的系统测试报告：
- `docs/03-系统测试报告.md`
4. 在 `docs/03-系统测试报告.md` 中粘贴关键指标与结论。

## 6. 常见问题
1. 未配置 LLM Key：
- 现象：`llm_summary` 为 fallback 文案。
- 处理：检查 `.env` 是否被 compose 读取。

2. 网关请求失败：
- 现象：HTTP 502。
- 处理：检查各服务 `/health` 与容器日志。

3. Docker 不可用：
- 处理：先在可用环境完成联调并保留结果产物，再回传到项目目录。
