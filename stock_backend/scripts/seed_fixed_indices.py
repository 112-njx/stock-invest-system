"""执行 02_seed_fixed_indices.sql：固定大盘/行业指数入库（幂等 upsert）。

用法：python scripts/seed_fixed_indices.py
说明：需先执行 alembic upgrade head；行业指数 code 由 kline_init 同步任务按名称回填。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.db import get_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

_SEED_PATH = Path(__file__).resolve().parents[2] / "docs" / "sql" / "02_seed_fixed_indices.sql"


def main() -> None:
    if not _SEED_PATH.exists():
        raise FileNotFoundError(f"seed sql not found: {_SEED_PATH}")
    sql = _SEED_PATH.read_text(encoding="utf-8")
    db = get_session()
    try:
        db.execute(text(sql))
        db.commit()
        total = db.execute(text("SELECT count(*) FROM symbols WHERE is_fixed_index")).scalar_one()
        print(f"seed done, fixed indices = {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
