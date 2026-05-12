#!/usr/bin/env bash
set -e
# Architecture Assistant — Quick start without Docker
# Usage: bash start.sh [--with-frontend]

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Auto-load .env
if [ -f "$ROOT_DIR/.env" ]; then
  echo "[*] Loading .env..."
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

# Avoid system proxy for localhost
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}"
export no_proxy="${no_proxy:-localhost,127.0.0.1}"
export REQUIREMENTS_AGENT_URL="${REQUIREMENTS_AGENT_URL:-http://localhost:8001}"
export MATCHING_AGENT_URL="${MATCHING_AGENT_URL:-http://localhost:8002}"
export EVALUATION_AGENT_URL="${EVALUATION_AGENT_URL:-http://localhost:8003}"

echo "[*] Starting all services..."

python -m uvicorn services.knowledge_base.app.main:app --host 0.0.0.0 --port 8004 &
PID_KB=$!
python -m uvicorn services.requirements_agent.app.main:app --host 0.0.0.0 --port 8001 &
PID_REQ=$!
python -m uvicorn services.matching_agent.app.main:app --host 0.0.0.0 --port 8002 &
PID_MATCH=$!
python -m uvicorn services.evaluation_agent.app.main:app --host 0.0.0.0 --port 8003 &
PID_EVAL=$!

sleep 3
python -m uvicorn services.api_gateway.app.main:app --host 0.0.0.0 --port 8000 &
PID_GW=$!
sleep 2

if [ "${1:-}" = "--with-frontend" ]; then
  echo "[*] Starting frontend..."
  cd "$ROOT_DIR/frontend" && python -m http.server 3000 &
  PID_FE=$!
  echo "    Frontend: http://localhost:3000"
fi

echo ""
echo "============================================"
echo "  All services started!"
echo "  Gateway API docs: http://localhost:8000/docs"
echo "  Frontend:         http://localhost:3000 (if --with-frontend)"
echo ""
echo "  Stop with: kill $PID_KB $PID_REQ $PID_MATCH $PID_EVAL $PID_GW ${PID_FE:-}"
echo "============================================"

wait
