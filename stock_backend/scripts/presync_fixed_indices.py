"""启动预同步脚本（V0.2 1.1 / 3.1）：固定指数K线新鲜度检查 + 全量目录数量检查，过期则触发任务。

由 docker-entrypoint.sh 在容器启动时执行（幂等可重跑）；不阻塞主进程启动，
实际同步由 Celery sync worker 异步补齐，进度写 sync_status（前端轮询展示）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import sync_service  # noqa: E402


def main() -> int:
    presync = sync_service.maybe_presync_fixed_indices()
    print(f"[presync] fixed indices: {presync}")
    catalog = sync_service.maybe_catalog_sync()
    print(f"[presync] catalog: {catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
