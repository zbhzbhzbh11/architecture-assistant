import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests

MAINSTREAM = {
    "Layered Architecture",
    "Microservices",
    "Event-Driven Architecture",
}


def load_cases(dataset_path: Path) -> List[Dict[str, Any]]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_response(data: Dict[str, Any]) -> Dict[str, bool]:
    candidates = data.get("candidates", [])
    final_report = data.get("final_report", {})
    decision_basis = final_report.get("decision_basis", {})
    matrix = final_report.get("comparison_matrix", [])

    has_top3 = len(candidates) >= 3
    mainstream_covered = any(c.get("style") in MAINSTREAM for c in candidates)
    has_final = bool(final_report.get("recommended_style"))
    explainable = bool(decision_basis.get("rule_engine")) and "llm_summary" in decision_basis
    has_matrix = len(matrix) >= 3

    return {
        "has_top3": has_top3,
        "mainstream_covered": mainstream_covered,
        "has_final": has_final,
        "explainable": explainable,
        "has_matrix": has_matrix,
        "pass": all([has_top3, mainstream_covered, has_final, explainable, has_matrix]),
    }


def run_regression(gateway_url: str, dataset: List[Dict[str, Any]], timeout: int) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    for case in dataset:
        requirement = case["requirement"]
        t0 = time.perf_counter()
        try:
            resp = requests.post(
                gateway_url,
                json={"requirement": requirement},
                timeout=timeout,
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            if resp.status_code != 200:
                rows.append(
                    {
                        "id": case["id"],
                        "status": resp.status_code,
                        "latency_ms": latency_ms,
                        "pass": False,
                        "error": f"HTTP {resp.status_code}",
                    }
                )
                continue

            data = resp.json()
            checks = evaluate_response(data)

            rows.append(
                {
                    "id": case["id"],
                    "status": resp.status_code,
                    "latency_ms": latency_ms,
                    "recommended_style": data.get("final_report", {}).get("recommended_style"),
                    **checks,
                }
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            rows.append(
                {
                    "id": case["id"],
                    "status": 0,
                    "latency_ms": latency_ms,
                    "pass": False,
                    "error": str(exc),
                }
            )

    total = len(rows)
    passed = sum(1 for r in rows if r.get("pass"))
    avg_latency = round(sum(r.get("latency_ms", 0.0) for r in rows) / total, 2) if total else 0.0

    def ratio(key: str) -> float:
        ok = sum(1 for r in rows if r.get(key))
        return round(ok / total, 4) if total else 0.0

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "gateway_url": gateway_url,
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "avg_latency_ms": avg_latency,
        "metrics": {
            "top3_rate": ratio("has_top3"),
            "mainstream_coverage_rate": ratio("mainstream_covered"),
            "final_recommendation_rate": ratio("has_final"),
            "explainability_rate": ratio("explainable"),
            "matrix_rate": ratio("has_matrix"),
        },
    }

    return {"summary": summary, "rows": rows}


def to_markdown(result: Dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        "# 回归测试结果汇总",
        "",
        f"- 时间: {s['timestamp']}",
        f"- 网关: {s['gateway_url']}",
        f"- 总用例: {s['total_cases']}",
        f"- 通过用例: {s['passed_cases']}",
        f"- 通过率: {s['pass_rate']:.2%}",
        f"- 平均响应时延: {s['avg_latency_ms']} ms",
        "",
        "## 指标",
        f"- Top3 完整率: {s['metrics']['top3_rate']:.2%}",
        f"- 主流架构覆盖率: {s['metrics']['mainstream_coverage_rate']:.2%}",
        f"- 最终推荐产出率: {s['metrics']['final_recommendation_rate']:.2%}",
        f"- 决策可解释率: {s['metrics']['explainability_rate']:.2%}",
        f"- 对比矩阵产出率: {s['metrics']['matrix_rate']:.2%}",
        "",
        "## 明细",
        "| case_id | status | latency_ms | pass | recommended_style |",
        "|---|---:|---:|---|---|",
    ]

    for row in result["rows"]:
        lines.append(
            f"| {row.get('id')} | {row.get('status')} | {row.get('latency_ms')} | "
            f"{row.get('pass')} | {row.get('recommended_style', '-')} |"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run regression tests against gateway API")
    parser.add_argument("--gateway-url", default="http://localhost:8000/api/v1/recommend")
    parser.add_argument("--dataset", default="tests/datasets/requirements_cases.json")
    parser.add_argument("--out-dir", default="tests/results")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(dataset_path)
    result = run_regression(args.gateway_url, cases, args.timeout)

    json_path = out_dir / "regression_result.json"
    md_path = out_dir / "regression_summary.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(result))

    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")


if __name__ == "__main__":
    main()
