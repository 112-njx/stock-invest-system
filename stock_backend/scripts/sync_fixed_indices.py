"""同步固定指数（G/H 区）K线 + 实时快照数据。

背景：行情页 G/H 区固定指数（大盘 14 + 行业 35）默认无 K 线/快照数据，
前端将显示空白 K 线与 "--" 价格。本脚本一次性补齐：

- K线：对所有固定指数拉取日K（周期 1d，近 KLINE_INIT_DAYS 天）幂等入库。
  * A 股大盘指数走新浪 stock_zh_index_daily（东方财富被限流时的可靠降级，快）；
  * 其余指数走 EastMoneyProvider 自带重试/降级（被限流时可能同步 0 条，可稍后重跑）。
- 快照：调用 run_realtime_poll 拉取全部标的实时快照写 snapshot_realtime。

用法：
  python scripts/sync_fixed_indices.py                    # 同步全部固定指数
  python scripts/sync_fixed_indices.py --code 000001      # 仅同步指定代码
- 无需启动 Celery，直接连接本地 DB 运行；可重复执行（幂等 upsert）。
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 保证可从仓库根或 stock_backend 目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.data_providers.eastmoney import _to_sina_index  # noqa: E402
from app.data_providers.factory import get_provider  # noqa: E402
from app.models.symbol import Symbol  # noqa: E402
from app.repositories import kline_repo, symbol_repo  # noqa: E402
from app.services import sync_service  # noqa: E402
from app.utils.db import get_session  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_fixed_indices")


def fetch_daily_bars(provider, sym: Symbol, start: datetime, end: datetime):
    """取单个固定指数日K：A股大盘指数优先新浪（快），其余走 provider 重试/降级。"""
    sina = _to_sina_index(sym.code) if sym.type == "index" and sym.code else None
    if sina:
        bars = provider._fetch_sina_index_daily(sym.code, start, end)
        if bars:
            return bars
    sym_param, asset_type = sync_service._provider_params(sym)
    return provider.fetch_kline(sym_param, "1d", start, end, asset_type)


def main() -> None:
    parser = argparse.ArgumentParser(description="同步固定指数 K线与快照")
    parser.add_argument("--code", default=None, help="仅同步指定标的代码（如 000001），缺省同步全部固定指数")
    parser.add_argument("--days", type=int, default=730, help="K线拉取天数（默认取配置 KLINE_INIT_DAYS）")
    parser.add_argument("--skip-snapshot", action="store_true", help="跳过实时快照同步")
    args = parser.parse_args()
    settings = get_settings()
    days = args.days or settings.KLINE_INIT_DAYS

    db = get_session()
    try:
        if args.code:
            symbols = [symbol_repo.get_by_code(db, args.code)]
            symbols = [s for s in symbols if s and s.is_fixed_index]
            if not symbols:
                logger.error("未找到固定指数代码 %s", args.code)
                sys.exit(1)
        else:
            symbols = list(
                db.scalars(
                    select(Symbol).where(Symbol.is_fixed_index.is_(True)).order_by(Symbol.sort_order, Symbol.id)
                )
            )
        logger.info("待同步固定指数 %d 个", len(symbols))

        provider = get_provider()
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        total = 0
        for sym in symbols:
            bars = fetch_daily_bars(provider, sym, start, end)
            added = kline_repo.upsert_bars(db, "1d", sym.id, bars)
            total += added
            db.commit()  # 逐标地提交，中断/限流时已同步部分不丢失
            status = "ok" if bars else "EMPTY(被限流/无数据)"
            logger.info("日K %s(%s) %s 新增=%d", sym.name, sym.code or "(行业无code)", status, added)
        logger.info("K线同步完成，累计新增 %d 条", total)

        if not args.skip_snapshot:
            result = sync_service.run_realtime_poll()
            logger.info("实时快照同步完成: %s", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
