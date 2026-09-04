"""等待 api 容器单点完成 alembic 迁移后再启动 worker/beat。

背景：api/worker/beat 共用同一 entrypoint，若三者并发执行 `alembic upgrade head`，
会并发建表撞 `pg_type_typname_nsp_index` 唯一约束。现仅 api（RUN_MIGRATIONS=1）执行迁移，
worker/beat 启动前轮询 alembic_version，直到当前版本 == head 再继续，避免并发竞态与"表不存在"。

用法：python scripts/wait_for_migrations.py
"""

import os
import sys
import time

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set")

    cfg = Config("alembic.ini")
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = create_engine(url, pool_pre_ping=True)

    for _ in range(60):  # 最长等待 120s
        try:
            with engine.connect() as conn:
                current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if current == head:
                print(f"[entrypoint] migrations ready (current={current}, head={head})")
                return 0
            print(f"[entrypoint] waiting migrations: current={current} head={head}")
        except Exception:  # noqa: BLE001  迁移尚未建表时 alembic_version 不存在
            print("[entrypoint] waiting for alembic_version table ...")
        time.sleep(2)

    sys.exit("[entrypoint] migrations not ready after 120s")


if __name__ == "__main__":
    raise SystemExit(main())
