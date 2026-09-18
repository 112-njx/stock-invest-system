#!/usr/bin/env bash
# G05 · P1-1 备份完整性验证：把最近一次全量备份恢复到一个临时库，校验完整后删除临时库。
#
# 由 Celery beat 每周日 03:30 调用（app/worker/tasks/backup_tasks.py），也可人工执行。
# 未通过时退出码 1 —— 说明备份不可用，必须立即排查（磁盘损坏 / dump 被截断 / 恢复报错）。
#
# 用法：
#   bash scripts/verify_backup.sh              # 验证最近一次全量备份
#   BACKUP_VERIFY_DB=stock_verify bash scripts/verify_backup.sh   # 换临时库名
#
# 校验口径（对活库成立的不变式，不是"行数完全相等"——那会在生产每周演练误报）：
#   ① pg_restore 退出码 0 且无 error 行；② 归档可读且条目数 > 0；
#   ③ 恢复库 public schema 表数与源库一致（schema 完整）；
#   ④ 抽样表 restored <= source（恢复库不可能比源库"更新"）；
#   ⑤ 源库非空时 restored > 0（dump 确实带了数据）。
# drift（source - restored）为信息项：活库上 > 0 属正常（dump 之后的写入）。
# 需要精确相等时，先停 api/worker/beat 再执行本脚本，届时 drift 应为 0。
set -euo pipefail

cd "$(dirname "$0")/.."  # → stock_backend/

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x ".venv/Scripts/python.exe" ]; then
    PYTHON_BIN=".venv/Scripts/python.exe"
  elif [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

exec "$PYTHON_BIN" -m app.services.backup_service verify
