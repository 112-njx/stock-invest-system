"""行情查询服务：标的列表/搜索、K线（Redis 缓存）、最新本地行情。"""

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_providers.factory import get_provider
from app.models.kline import KLINE_MODELS, Kline1d
from app.models.symbol import Symbol
from app.repositories import kline_repo, symbol_repo
from app.utils import market_cache

logger = logging.getLogger(__name__)


def list_symbols(
    db: Session,
    type_: str | None = None,
    search: str | None = None,
    fixed_only: bool | None = None,
) -> list[Symbol]:
    return symbol_repo.list_symbols(db, type_=type_, search=search, fixed_only=fixed_only)


def search_symbols(db: Session, q: str, type_: str | None = None, limit: int = 10) -> list[dict]:
    """搜索联想（V0.2 三层）：精确代码 → 目录模糊（已同步优先）→ 外部回退。

    结果按「精确匹配 > is_catalog=FALSE(已同步) > is_catalog=TRUE(仅目录)」排序再按 code，
    附带 is_catalog / has_kline 标注；结果 Redis 缓存（TTL 3600，catalog_sync 后失效）。
    """
    q = q.strip()
    if not q:
        return []
    cached = market_cache.get_search_cache(type_, q)
    if cached is not None:
        return cached
    rows = _query_search_rows(db, q, type_, limit)
    if not rows and (type_ in (None, "stock")):
        # 外部回退：akshare 实时过滤，写入目录（is_catalog=True）+ 缓存，再重查本地
        from app.utils.redis_client import get_redis_client

        redis = get_redis_client()
        miss_key = f'provider:search-miss:{type_ or "all"}:{q}'
        ext = get_provider().search_ak_stock(q, limit) if redis.set(miss_key, '1', nx=True, ex=3600) else []
        if ext:
            symbol_repo.upsert_catalog_symbols(db, [(c, n, "stock", "SSE") for c, n in ext])
            db.commit()
            rows = _query_search_rows(db, q, type_, limit)
    result = [_search_row(db, s) for s in rows]
    if result:
        market_cache.set_search_cache(type_, q, result)
    return result


def _query_search_rows(db: Session, q: str, type_: str | None, limit: int) -> list[Symbol]:
    """精确代码优先；否则目录模糊（code 前缀 / name 子串），按 is_catalog+code 排序。"""
    exact = list(db.scalars(select(Symbol).where(Symbol.code == q).order_by(Symbol.id).limit(limit)))
    if exact:
        return exact
    stmt = select(Symbol).where(Symbol.code.like(f"{q}%") | Symbol.name.like(f"%{q}%"))
    if type_:
        stmt = stmt.where(Symbol.type == type_)
    stmt = stmt.order_by(Symbol.is_catalog, Symbol.code).limit(limit)
    return list(db.scalars(stmt))


def _search_row(db: Session, s: Symbol) -> dict:
    """搜索行：Symbol 字段 + is_catalog/has_kline 标注。"""
    has = s.id in _kline_symbol_ids(db, [s.id])
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "type": s.type,
        "market": s.market,
        "industry": s.industry,
        "etf_linked": s.etf_linked,
        "is_fixed_index": s.is_fixed_index,
        "sort_order": s.sort_order,
        "is_catalog": s.is_catalog,
        "has_kline": has,
    }


def _kline_symbol_ids(db: Session, ids: list[int]) -> set[int]:
    """命中 K 线的标的 id 集合（kline_1d 存在即视为有数据）。"""
    if not ids:
        return set()
    from app.services.market_policy import akshare_enabled
    query = select(Kline1d.symbol_id).where(Kline1d.symbol_id.in_(ids))
    if not akshare_enabled():
        query = query.where(Kline1d.source == 'stockdb')
    return set(db.scalars(query.distinct()))


def has_kline(db: Session, symbol_id: int) -> bool:
    """标的是否已有 K 线（关注添加自动同步判定用）。"""
    return symbol_id in _kline_symbol_ids(db, [symbol_id])


def resolve_symbol_id(db: Session, symbol: str) -> int | None:
    """按代码解析 symbol_id；代码不存在时回退按 id 解析。"""
    sym = symbol_repo.get_by_code(db, symbol)
    if sym:
        return sym.id
    if symbol.isdigit():
        return int(symbol)
    return None


def get_kline(
    db: Session,
    symbol: str,
    period: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    """K 线查询：默认区间（未显式 start/end）走"最近N根"Redis 缓存，未命中回源 PG 并回写。

    显式指定 start/end/offset 时直查 PG（保证范围正确性，不参与缓存）。
    返回统一 dict 列表（ts 为 ISO 字符串），供 API/前端渲染。
    """
    if period not in (*KLINE_MODELS.keys(), "1w", "1mon"):
        raise ValueError(f"unsupported period: {period}")
    symbol_id = resolve_symbol_id(db, symbol)
    if symbol_id is None:
        return []
    use_cache = start is None and end is None and offset == 0
    if use_cache:
        cached = market_cache.get_kline_cache(symbol_id, period, limit)
        if cached is not None:
            logger.info("[kline-cache] hit %s:%s:%s", symbol_id, period, limit)
            return cached
        # 缓存击穿保护：未获取锁的请求等待后读缓存，仍无则回源（Redis 不可用直接放行）
        if not market_cache.acquire_kline_lock(symbol_id, period):
            time.sleep(2)
            cached = market_cache.get_kline_cache(symbol_id, period, limit)
            if cached is not None:
                return cached
        try:
            bars = kline_repo.latest_bars(db, period, symbol_id, limit=limit)
            data = [market_cache.kline_bar_to_dict(b) for b in bars]
            market_cache.set_kline_cache(symbol_id, period, limit, data)
            return data
        finally:
            market_cache.release_kline_lock(symbol_id, period)
    if end is None:
        end = datetime.now().astimezone()
    if start is None:
        start = end - timedelta(days=365)
    bars = kline_repo.get_bars(db, period, symbol_id, start, end, limit=limit, offset=offset)
    return [market_cache.kline_bar_to_dict(b) for b in bars]


def get_latest_quotes(db: Session, symbol_ids: list[int]) -> list[dict]:
    from app.services import local_quotes, market_policy
    symbols = list(db.scalars(select(Symbol).where(Symbol.id.in_(symbol_ids))))
    rows = local_quotes.quotes(db, symbols)
    revision = market_policy.read()['revision']
    for row in rows:
        row['policy_revision'] = revision
    return rows
