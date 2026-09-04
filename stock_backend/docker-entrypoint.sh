#!/bin/sh
# 容器启动入口：等待 DB 就绪 → 仅 api(RUN_MIGRATIONS=1) 单点执行 Alembic 迁移+固定指数种子+presync，
# worker/beat 等待迁移到 head 后再启动主进程（避免多容器并发迁移撞唯一约束、presync 重复触发）。
set -e

echo "[entrypoint] waiting for database..."
python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit("DATABASE_URL not set")
engine = create_engine(url, pool_pre_ping=True)
for _ in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[entrypoint] database ready")
        break
    except OperationalError:
        time.sleep(2)
else:
    sys.exit("[entrypoint] database not ready after 120s")
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] applying migrations (single-point by api)..."
  alembic upgrade head

  echo "[entrypoint] seeding fixed indices..."
  python scripts/seed_fixed_indices.py

  echo "[entrypoint] checking fixed indices presync..."
  python scripts/presync_fixed_indices.py || echo "[entrypoint] presync check failed (skip, worker will sync on schedule)"
else
  echo "[entrypoint] waiting for api to finish migrations..."
  python scripts/wait_for_migrations.py
fi

echo "[entrypoint] starting: $*"
exec "$@"
