# -*- coding: utf-8 -*-
"""实测行情服务核心路径耗时：Redis 缓存命中（get_snapshots）+ K线读取"""
import sys, time, statistics
sys.path.insert(0, '.')
from app.utils.db import SessionLocal
from app.services import market_service
from app.repositories import kline_repo

db = SessionLocal()
SYMBOLS = [125, 11825, 73, 74]  # 贵州茅台/赛力斯/上证指数/沪深300

def bench(fn, n=200, label=""):
    # 预热
    for _ in range(5):
        fn()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    avg = statistics.mean(times)
    p50 = times[len(times)//2]
    p95 = times[int(len(times)*0.95)-1]
    p99 = times[int(len(times)*0.99)-1]
    print(f"{label}: n={n} min={times[0]:.3f}ms avg={avg:.3f}ms p50={p50:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms max={times[-1]:.3f}ms")

if __name__ == "__main__":
    # 1. 单标的快照（Redis 缓存命中）——模拟点击个股详情加载基本数据
    bench(lambda: market_service.get_snapshots(db, [125]), 200, "单标的快照(Redis命中) 600519")
    bench(lambda: market_service.get_snapshots(db, [11825]), 200, "单标的快照(Redis命中) 601127")
    # 2. 多标的快照（关注列表/行情面板）
    bench(lambda: market_service.get_snapshots(db, SYMBOLS), 200, "4标的批量快照")
    # 3. K线读取（点击个股加载图表）
    bench(lambda: kline_repo.get_bars(db, "1d", 125, None, None, limit=250), 100, "K线读取 600519 250根")
    bench(lambda: kline_repo.get_bars(db, "1d", 11825, None, None, limit=250), 100, "K线读取 601127 250根")
    db.close()
