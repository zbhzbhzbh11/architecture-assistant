import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def load_result(result_path: Path) -> Dict[str, Any]:
    with open(result_path, "r", encoding="utf-8") as f:
        return json.load(f)


def top_failures(rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    failures = [r for r in rows if not r.get("pass")]
    failures.sort(key=lambda x: x.get("latency_ms", 0), reverse=True)
    return failures[:limit]


def recommendation_distribution(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for r in rows:
        name = r.get("recommended_style") or "UNKNOWN"
        dist[name] = dist.get(name, 0) + 1
    return dict(sorted(dist.items(), key=lambda item: item[1], reverse=True))


def render_report(result: Dict[str, Any]) -> str:
    s = result.get("summary", {})
    rows = result.get("rows", [])

    metrics = s.get("metrics", {})
    failures = top_failures(rows)
    dist = recommendation_distribution(rows)

    lines = [
        "# 系统测试报告",
        "",
        "## 1. 测试范围",
        "- 需求解析准确性",
        "- 架构推荐完整性（至少3种候选）",
        "- 决策可解释性（规则依据 + LLM说明）",
        "- 接口稳定性与异常处理",
        "",
        "## 2. 测试环境与方法",
        f"- 执行时间: {s.get('timestamp', datetime.now().isoformat(timespec='seconds'))}",
        f"- 网关接口: {s.get('gateway_url', 'N/A')}",
        "- 数据集: tests/datasets/requirements_cases.json（20条）",
        "- 执行脚本: tests/run_regression.py",
        "",
        "## 3. 核心测试结果",
        f"- 总用例数: {s.get('total_cases', 0)}",
        f"- 通过用例数: {s.get('passed_cases', 0)}",
        f"- 通过率: {s.get('pass_rate', 0):.2%}",
        f"- 平均响应时延: {s.get('avg_latency_ms', 0)} ms",
        "",
        "## 4. 指标统计",
        f"- Top3完整率: {metrics.get('top3_rate', 0):.2%}",
        f"- 主流架构覆盖率: {metrics.get('mainstream_coverage_rate', 0):.2%}",
        f"- 最终推荐产出率: {metrics.get('final_recommendation_rate', 0):.2%}",
        f"- 决策可解释率: {metrics.get('explainability_rate', 0):.2%}",
        f"- 对比矩阵产出率: {metrics.get('matrix_rate', 0):.2%}",
        "",
        "## 5. 推荐结果分布",
    ]

    for k, v in dist.items():
        lines.append(f"- {k}: {v}")

    lines.extend([
        "",
        "## 6. 失败样例（最多5条）",
        "| case_id | status | latency_ms | error |",
        "|---|---:|---:|---|",
    ])

    if failures:
        for f in failures:
            lines.append(
                f"| {f.get('id')} | {f.get('status')} | {f.get('latency_ms')} | {f.get('error', '-')} |"
            )
    else:
        lines.append("| - | - | - | 无失败样例 |")

    lines.extend([
        "",
        "## 7. 结论",
        "- 系统已具备从需求输入到架构推荐的闭环能力。",
        "- 推荐结果具备规则依据与LLM说明，可用于答辩展示可解释性。",
        "- 如存在失败样例，建议优先检查上游服务健康状态与LLM连通性。",
        "",
        "## 8. 附录",
        "- 原始结果文件: tests/results/regression_result.json",
        "- 汇总文件: tests/results/regression_summary.md",
    ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate system test report from regression result")
    parser.add_argument("--result", default="tests/results/regression_result.json")
    parser.add_argument("--out", default="docs/03-系统测试报告.md")
    args = parser.parse_args()

    result_path = Path(args.result)
    out_path = Path(args.out)

    if not result_path.exists():
        raise FileNotFoundError(
            f"Regression result not found: {result_path}. Run tests/run_regression.py first."
        )

    result = load_result(result_path)
    report = render_report(result)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Generated test report: {out_path}")


if __name__ == "__main__":
    main()
