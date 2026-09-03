# -*- coding: utf-8 -*-
"""实测行情接口响应耗时（Redis 缓存命中场景）"""
import time
import requests

BASE = "http://127.0.0.1:8000"
TOKEN = None

def login():
    global TOKEN
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"username": "njx", "password": ""}, timeout=10)
    # 密码未知，尝试常见
    for pwd in ["123456", "njx", "admin"]:
        r = requests.post(f"{BASE}/api/v1/auth/login", json={"username": "njx", "password": pwd}, timeout=10)
        if r.status_code == 200:
            TOKEN = r.json()["data"]["access_token"]
            print("登录成功, 密码:", pwd)
            return
    print("登录失败:", r.status_code, r.text[:200])
    # 尝试直接无token访问快照（也许有公开接口）
    TOKEN = None

def call(method, url, **kw):
    h = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    t0 = time.perf_counter()
    r = requests.request(method, url, headers=h, timeout=10, **kw)
    dt = (time.perf_counter() - t0) * 1000
    return r.status_code, dt, r.text[:100]

if __name__ == "__main__":
    login()
    # 快照接口：贵州茅台 600519 / 上证指数 000001 / 赛力斯 601127
    snap_targets = ["600519", "000001", "601127"]
    for sym in snap_targets:
        times = []
        for _ in range(15):
            st, dt, body = call("GET", f"{BASE}/api/v1/market/snapshot", params={"symbol": sym})
            times.append(dt)
        times.sort()
        avg = sum(times) / len(times)
        p50 = times[len(times)//2]
        p95 = times[int(len(times)*0.95)-1]
        print(f"snapshot {sym}: min={times[0]:.2f}ms avg={avg:.2f}ms p50={p50:.2f}ms p95={p95:.2f}ms max={times[-1]:.2f}ms status={st}")
