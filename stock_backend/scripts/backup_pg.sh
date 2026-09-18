#!/usr/bin/env bash
# G05 · P1-1 PostgreSQL 每日全量备份 + 保留期清理 + 文件镜像 + 异地同步。
#
# 与 Celery beat 任务（app/worker/tasks/backup_tasks.py）共用同一实现
# （app/services/backup_service.py），本脚本供人工执行 / 系统 cron / 容器内独立调用，
# 避免"脚本一套逻辑、任务另一套逻辑"分叉。
#
# 用法：
#   bash scripts/backup_pg.sh            # 全量备份（默认）
#   bash scripts/backup_pg.sh dump       # 仅 PostgreSQL 逻辑全量（pg_dump -Fc）
#   bash scripts/backup_pg.sh base       # 仅物理基础备份（pg_basebackup，PITR 基线）
#   bash scripts/backup_pg.sh files      # 仅文件镜像
#   bash scripts/backup_pg.sh offsite    # 仅异地同步
#   bash scripts/backup_pg.sh prune      # 仅按保留期清理
#   bash scripts/backup_pg.sh status     # 查看最近一次备份状态
#
# 退出码：0 成功 / 1 备份失败（可用于告警联动）/ 2 参数错误。
#
# 依赖环境变量（见 app/core/config.py BACKUP_* 组，均有默认值）：
#   BACKUP_DIR                备份根目录（容器 /backup，本地 data/backups）
#   BACKUP_PG_DUMP_MODE       auto | local | docker（宿主开发环境本机无 PG 客户端，auto 会退回 docker）
#   BACKUP_PG_CONTAINER       docker 模式借用的 PG 容器名
#   BACKUP_PG_RETAIN_DAYS     全量保留天数（默认 30）
#   RCLONE_REMOTE             对象存储远端；为空时异地备份进入模拟模式
set -euo pipefail

cd "$(dirname "$0")/.."  # → stock_backend/

# Python 解释器：容器内为 python；本地开发优先用工程虚拟环境
if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x ".venv/Scripts/python.exe" ]; then
    PYTHON_BIN=".venv/Scripts/python.exe"
  elif [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

ACTION="${1:-full}"
exec "$PYTHON_BIN" -m app.services.backup_service "$ACTION"
