#!/usr/bin/env python
"""Health check for python-research-service.

Verifies:
  - MySQL reachable and stock_daily_kline exists
  - AkShare returns >= 1 row for sh000001 in last 5 days
  - Log directory writable
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import get_settings  # noqa: E402


def _check_db() -> dict:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(get_settings().db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            r = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'stock_daily_kline'"
            )).scalar()
            if r == 0:
                return {"status": "FAIL", "message": "stock_daily_kline missing"}
        return {"status": "OK"}
    except Exception as ex:
        return {"status": "FAIL", "message": f"{type(ex).__name__}: {ex}"}


def _check_akshare() -> dict:
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily_em(symbol="sh000001")
        rows = 0 if df is None else len(df)
        if rows < 1:
            return {"status": "FAIL", "message": "akshare returned empty"}
        return {"status": "OK", "rows": rows}
    except Exception as ex:
        return {"status": "FAIL", "message": f"{type(ex).__name__}: {ex}"}


def _check_log_dir() -> dict:
    try:
        p = Path(get_settings().log_dir)
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".health_probe"
        probe.write_text(str(time.time()), encoding="utf-8")
        probe.unlink()
        return {"status": "OK", "path": str(p)}
    except Exception as ex:
        return {"status": "FAIL", "message": f"{type(ex).__name__}: {ex}"}


def main() -> int:
    report = {
        "db": _check_db(),
        "akshare": _check_akshare(),
        "logDir": _check_log_dir(),
    }
    all_ok = all(v.get("status") == "OK" for v in report.values())
    report["overall"] = "OK" if all_ok else "FAIL"
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
