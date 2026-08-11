#!/usr/bin/env bash
# 开发阶段容器残留一键清理脚本（在项目根目录或任意位置运行均可）
#
# 作用：停止并删除开发栈容器/网络/孤儿容器，删除 dev 镜像、悬空镜像与 Docker 构建缓存，
#       避免反复改动前端/后端文件、多次 docker compose up --build 造成的容器文件残留。
# 默认保留 pgdata/redisdata 数据卷（开发数据不丢）；
# 追加 -f（或 --full）连数据卷一并清空，实现 100% 无残留（重启后自动 alembic 迁移 + 幂等种子）。
#
# 用法：
#   bash deploy/cleanup_dev.sh          # 常规清理（保留数据卷）
#   bash deploy/cleanup_dev.sh -f       # 全量清理（连数据卷清空）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="deploy/docker-compose.dev.yml"

cd "${ROOT_DIR}"

DOWN_ARGS="--remove-orphans"
if [[ "${1:-}" == "-f" || "${1:-}" == "--full" ]]; then
  DOWN_ARGS+=" --volumes"
  echo "[cleanup] 全量清理：数据卷将一并删除（重启后自动迁移+种子）。"
fi

echo "[cleanup] 1/4 停止并删除开发栈容器、网络与孤儿容器..."
docker compose --env-file .env.docker -f "${COMPOSE_FILE}" down ${DOWN_ARGS} >/dev/null 2>&1 || true

echo "[cleanup] 2/4 删除开发镜像 stock-backend:dev..."
docker rmi stock-backend:dev >/dev/null 2>&1 || true

echo "[cleanup] 3/4 删除悬空镜像..."
docker image prune -f >/dev/null 2>&1 || true

echo "[cleanup] 4/4 清理 Docker 构建缓存..."
docker builder prune -f >/dev/null 2>&1 || true

echo "[cleanup] 完成：开发容器残留已清理。"
