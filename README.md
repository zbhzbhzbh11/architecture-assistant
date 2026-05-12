# Architecture Style Intelligent Assistant

A course project for "Software Architecture".

## Goals
- Analyze natural language requirements.
- Recommend at least 3 architecture styles.
- Generate explainable final decision reports.
- Keep architecture knowledge extensible.

## System Overview
- `api-gateway`: Orchestrates all agents and exposes unified API.
- `requirements-agent`: Extracts requirement features from user text.
- `matching-agent`: Applies rule-based scoring on knowledge base styles.
- `evaluation-agent`: Produces comparison and final recommendation.
- `knowledge-base`: Serves architecture style metadata (>=10 styles).
- `frontend`: Minimal web page for demo input/output flow.

## Quick Start
1. Install Docker Desktop.
2. In this folder, run:
   - `docker compose up --build`
3. Open:
   - Frontend: `http://localhost:3000`
   - Gateway API docs: `http://localhost:8000/docs`

## Regression Test
1. Install test dependency:
   - `pip install -r tests/requirements.txt`
2. Run regression script:
   - `python tests/run_regression.py --gateway-url http://localhost:8000/api/v1/recommend`
3. Outputs:
   - `tests/results/regression_result.json`
   - `tests/results/regression_summary.md`

## Unit Tests
1. Install test dependency:
   - `pip install -r tests/requirements.txt`
2. Run all unit tests:
   - `pytest tests/unit/ -v`
3. Run a single module:
   - `pytest tests/unit/test_requirements.py -v`
   - `pytest tests/unit/test_matching.py -v`
   - `pytest tests/unit/test_knowledge.py -v`
   - `pytest tests/unit/test_evaluation.py -v`
4. Coverage: 23 test cases across 4 test files covering all 3 agents + knowledge-base.

## API Flow
- `POST /api/v1/recommend`
  1. Gateway -> requirements-agent `/extract`
  2. Gateway -> matching-agent `/match`
  3. Gateway -> evaluation-agent `/evaluate`
  4. Return final report JSON

## Auto Check
```bash
# Install test dependency (if not installed):
pip install -r tests/requirements.txt

# Run auto assignment check:
python scripts/check_assignment.py --project-root .

# Output files:
#   docs/自动验收检查结果.md
#   docs/自动验收检查结果.json
```

## Repository Structure
- `services/`: Microservices source code.
- `tests/datasets/`: Requirement test cases (>=20).
- `docs/`: Requirement spec, architecture design, test report drafts.
- `scripts/`: Automation utilities (auto-check, etc.).
