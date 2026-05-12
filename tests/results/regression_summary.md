# 回归测试结果汇总

- 时间: 2026-05-12T19:08:59
- 网关: http://localhost:8000/api/v1/recommend
- 总用例: 20
- 通过用例: 19
- 通过率: 95.00%
- 平均响应时延: 50877.27 ms

## 指标
- Top3 完整率: 95.00%
- 主流架构覆盖率: 95.00%
- 最终推荐产出率: 95.00%
- 决策可解释率: 95.00%
- 对比矩阵产出率: 95.00%

## 明细
| case_id | status | latency_ms | pass | recommended_style |
|---|---:|---:|---|---|
| 1 | 200 | 16045.82 | True | Event-Driven Architecture |
| 2 | 200 | 27435.98 | True | Microservices |
| 3 | 200 | 32380.25 | True | Layered Architecture |
| 4 | 200 | 28740.86 | True | Event-Driven Architecture |
| 5 | 200 | 21856.62 | True | Microservices |
| 6 | 200 | 36562.77 | True | Event-Driven Architecture |
| 7 | 200 | 27161.11 | True | Event-Driven Architecture |
| 8 | 200 | 28142.16 | True | Event-Driven Architecture |
| 9 | 200 | 22202.71 | True | Client-Server |
| 10 | 200 | 19692.5 | True | Microservices |
| 11 | 200 | 31594.11 | True | SOA |
| 12 | 200 | 34457.77 | True | Event-Driven Architecture |
| 13 | 200 | 36366.59 | True | Event-Driven Architecture |
| 14 | 200 | 27026.93 | True | Layered Architecture |
| 15 | 200 | 25733.53 | True | Event-Driven Architecture |
| 16 | 200 | 28757.81 | True | Event-Driven Architecture |
| 17 | 200 | 15449.81 | True | Event-Driven Architecture |
| 18 | 200 | 32425.2 | True | Pipeline-Filter |
| 19 | 502 | 493503.4 | False | - |
| 20 | 200 | 32009.42 | True | Microservices |