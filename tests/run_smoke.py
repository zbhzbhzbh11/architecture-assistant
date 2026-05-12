import json
from pathlib import Path

import requests

DATASET = Path(__file__).parent / "datasets" / "requirements_cases.json"
GATEWAY_URL = "http://localhost:8000/api/v1/recommend"


def main() -> None:
    with open(DATASET, "r", encoding="utf-8") as f:
        cases = json.load(f)

    passed = 0
    for case in cases:
        resp = requests.post(GATEWAY_URL, json={"requirement": case["requirement"]}, timeout=30)
        ok = resp.status_code == 200 and "final_report" in resp.json()
        print(f"case={case['id']} status={resp.status_code} pass={ok}")
        if ok:
            passed += 1

    print(f"passed {passed}/{len(cases)}")


if __name__ == "__main__":
    main()
