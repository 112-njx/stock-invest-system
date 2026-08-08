"""手动触发首次全量K线同步（kline_init）。

用法：
  python scripts/run_kline_init.py              # 全部可同步标的
  python scripts/run_kline_init.py --symbol 1    # 指定 symbol_id
  python scripts/run_kline_init.py --days 730    # 指定回看天数
  python scripts/run_kline_init.py --async       # 投递到 Celery（需 worker 运行）

说明：需先执行 1.6 种子数据（固定指数入库）后才有标的可同步。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402

setup_logging()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=int, default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--async", dest="use_celery", action="store_true")
    args = parser.parse_args()

    if args.use_celery:
        from app.worker.tasks.sync_tasks import kline_init

        result = kline_init.delay(symbol_id=args.symbol, days=args.days)
        print(f"queued kline_init task_id={result.id}")
    else:
        from app.services.sync_service import run_kline_init

        result = run_kline_init(symbol_id=args.symbol, days=args.days)
        print(f"kline_init done: {result}")


if __name__ == "__main__":
    main()
