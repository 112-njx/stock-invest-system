"""Synchronize fixed-index history using the application source/storage policy.

Run from stock_backend: python scripts/sync_fixed_indices.py [--code 801790.SL]
Update StockDB with 数据更新.exe first; the SDK bridge is required for SW indices.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.repositories import symbol_repo  # noqa: E402
from app.services import sync_service  # noqa: E402
from app.utils.db import get_session  # noqa: E402

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='按项目当前策略同步固定指数历史 K 线')
    parser.add_argument('--code', help='固定指数代码；不指定时同步所有支持的固定指数')
    args = parser.parse_args()
    if args.code:
        with get_session() as db:
            symbol = symbol_repo.get_by_code(db, args.code)
            if symbol is None or not symbol.is_fixed_index:
                parser.error('未找到该固定指数')
            if not sync_service.supported_symbol(symbol):
                parser.error('当前数据源策略不支持该指数')
            symbol_id = symbol.id
        result = sync_service.run_kline_init(symbol_id=symbol_id, days=get_settings().KLINE_INIT_DAYS)
    else:
        result = sync_service.run_fixed_indices_sync(skip_existing=False)
        if any('error' in item for item in result.values()):
            raise RuntimeError(f'固定指数同步存在失败：{result}')
    logger.info('固定指数同步完成：%s', result)
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
