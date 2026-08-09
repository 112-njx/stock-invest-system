"""阶段二 API 冒烟测试：起本服务后运行 `python scripts/smoke_phase2.py`。

覆盖：注册→登录→users/me→watchlist 增删→support-resistance 增删→indicators。
退出前清理测试用户。用法：uvicorn 启动后单独跑本脚本。
"""

import os
import sys
import uuid
from pathlib import Path

import httpx

# 使 `python scripts/smoke_phase2.py` 可导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = os.getenv("SMOKE_BASE", "http://127.0.0.1:8010")
UNAME = f"smoke2_{uuid.uuid4().hex[:6]}"


def _check(step: str, resp: httpx.Response):
    body = resp.json()
    ok = resp.status_code == 200 and body.get("code") == 0
    print(f"[{'OK' if ok else 'FAIL'}] {step}: {resp.status_code} {str(body)[:120]}")
    assert ok, f"{step} failed: {body}"


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10) as c:
        r = c.post("/api/v1/auth/register", json={"username": UNAME, "password": "pass123456", "nickname": "冒烟"})
        _check("注册", r)
        token = r.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = c.post("/api/v1/auth/login", json={"username": UNAME, "password": "pass123456"})
        _check("登录", r)

        r = c.get("/api/v1/users/me", headers=headers)
        _check("users/me", r)
        assert r.json()["data"]["username"] == UNAME

        r = c.put("/api/v1/users/me", headers=headers, json={"nickname": "改名了"})
        _check("users/me 更新", r)
        assert r.json()["data"]["nickname"] == "改名了"

        r = c.post("/api/v1/watchlist", headers=headers, json={"symbol": "600519"})
        _check("watchlist 添加", r)
        wid = r.json()["data"]["id"]

        r = c.get("/api/v1/watchlist", headers=headers)
        _check("watchlist 列表", r)
        assert len(r.json()["data"]) == 1

        r = c.delete(f"/api/v1/watchlist/{wid}", headers=headers)
        _check("watchlist 删除", r)

        r = c.post("/api/v1/support-resistance", headers=headers, json={"symbol": "600519", "type": "support", "price": 1200, "note": "强支撑"})
        _check("支撑压力位添加", r)
        sr_id = r.json()["data"]["id"]

        r = c.get("/api/v1/support-resistance", headers=headers, params={"symbol_id": r.json()["data"]["symbol_id"]})
        _check("支撑压力位列表", r)

        r = c.delete(f"/api/v1/support-resistance/{sr_id}", headers=headers)
        _check("支撑压力位删除", r)

        r = c.get("/api/v1/indicators", params={"symbol": "600519", "period": "1d", "names": "macd,kdj"})
        _check("指标查询", r)
        row = r.json()["data"][-1]
        assert all(k in row for k in ("macd_dif", "macd_dea", "macd_hist", "kdj_k"))

        # 无 token 访问受保护接口应 401
        r = c.get("/api/v1/watchlist")
        assert r.status_code == 401, f"期望 401，实际 {r.status_code}"
        print("[OK] 未登录访问 watchlist 返回 401")

        # 清理测试用户（直接删库，级联删除关注/支撑压力位）
        from app.models.user import User
        from app.utils.db import get_session

        db = get_session()
        try:
            u = db.query(User).filter(User.username == UNAME).first()
            if u:
                db.delete(u)
                db.commit()
        finally:
            db.close()
    print(f"\n全部通过，测试用户 {UNAME} 已清理")


if __name__ == "__main__":
    main()
