#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "未找到可用的虚拟环境 Python: ${VENV_PYTHON}"
  echo "请先创建并初始化项目虚拟环境。"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "未找到 npm，请先安装 Node.js/npm。"
  exit 1
fi

if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  echo "前端依赖尚未安装，请先执行："
  echo "cd \"${FRONTEND_DIR}\" && npm install"
  exit 1
fi

backend_pid=""
frontend_pid=""

cleanup() {
  local exit_code=$?

  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" >/dev/null 2>&1; then
    kill "${frontend_pid}" >/dev/null 2>&1 || true
  fi

  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" >/dev/null 2>&1; then
    kill "${backend_pid}" >/dev/null 2>&1 || true
  fi

  wait >/dev/null 2>&1 || true
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

PYTHONPATH="${PROJECT_ROOT}/backend" \
  "${VENV_PYTHON}" -m uvicorn app.main:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --log-level warning &
backend_pid=$!

(
  cd "${FRONTEND_DIR}"
  npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" --clearScreen false
) &
frontend_pid=$!

echo "开发环境启动中。前端: http://${FRONTEND_HOST}:${FRONTEND_PORT}  后端: http://${BACKEND_HOST}:${BACKEND_PORT}  按 Ctrl+C 可同时关闭前后端。"

wait -n "${backend_pid}" "${frontend_pid}"
