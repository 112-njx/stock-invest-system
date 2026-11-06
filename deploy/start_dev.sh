#!/usr/bin/env bash
# 开发阶段一键启动：先一键清理容器残留，再构建并启动开发栈。
#
# 用法：
#   bash deploy/start_dev.sh            # 常规启动（保留数据卷）
#   bash deploy/start_dev.sh --clean-data  # 连数据卷一并清空后启动（100% 无残留）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "[start] 清理开发容器残留..."
CLEAN_ARGS=()
if [[ "${1:-}" == "--clean-data" ]]; then CLEAN_ARGS=(-f); fi
bash "${SCRIPT_DIR}/cleanup_dev.sh" "${CLEAN_ARGS[@]:-}"

echo "[start] 构建并启动开发栈（首次构建含 pip 安装，请耐心等待）..."
docker compose --env-file .env.docker -f "${SCRIPT_DIR}/docker-compose.dev.yml" up -d --build

echo "[start] 完成。"
echo "  后端 API ：http://127.0.0.1:8000  （uvicorn --reload，改源码自动热重载）"
echo "  前端页面 ：http://127.0.0.1:8081  （构建式：node 自动 build → nginx，/api 反代到 api）"
echo "  查看日志 ：docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml logs -f api"
