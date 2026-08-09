"""阶段四冒烟测试：发起回测 → Celery 异步执行 → 轮询状态 → 查询结果 全流程。

用法：
1. `uvicorn app.main:app` 启动 API；
2. `celery -A app.worker.celery_app:celery_app worker -Q backtest --pool=solo` 启动回测 worker；
3. 运行 `python scripts/smoke_phase4.py`。
- 自动注册临时用户、finally 清理测试数据；
- 需标的已有 K 线数据（如贵州茅台 600519，可用同步任务或阶段一数据）。
"""

import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
_PREFIX = "smoke4_"

_SMA_STRATEGY = '''
def initialize(context):
    context.fast = int(context.params.get("entry", {}).get("fast", 5))
def on_bar(bar, context):
    closes = context.closes
    if len(closes) < context.fast:
        return
    ma = sum(closes[-context.fast:]) / context.fast
    if bar["close"] > ma and context.pos == 0:
        context.buy()
    elif bar["close"] < ma and context.pos > 0:
        context.sell()
'''


def _req(method: str, path: str, token: str | None = None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.request(method, BASE + path, headers=headers, timeout=60, **kw)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    return r.status_code, body


def main() -> int:
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    print(f"== 阶段四冒烟：用户 {uname} ==")
    try:
        # 1) 注册
        s, data = _req("POST", "/api/v1/auth/register", json={"username": uname, "password": "pass123456"})
        assert s == 200 and data["code"] == 0, data
        token = data["data"]["token"]
        print("[ok] 注册")

        # 2) 保存双均线策略
        s, data = _req("POST", "/api/v1/strategies", token,
                       json={"title": "双均线", "description": "金叉买死叉卖", "code": _SMA_STRATEGY,
                             "params": {"entry": {"fast": 5}}, "status": "active"})
        assert s == 200 and data["code"] == 0, data
        sid = data["data"]["id"]
        print(f"[ok] 策略保存 strategy_id={sid}")

        # 3) 发起回测（贵州茅台，日K）
        s, data = _req("POST", "/api/v1/backtest", token,
                       json={"strategy_id": sid, "symbol": "600519", "period": "1d"})
        assert s == 200 and data["code"] == 0, data
        task_id = data["data"]["id"]
        print(f"[ok] 发起回测 task_id={task_id} status={data['data']['status']}")

        # 4) 轮询任务状态（模拟前端轮询）
        deadline = time.time() + 90
        status = None
        while time.time() < deadline:
            s, data = _req("GET", f"/api/v1/backtest/tasks/{task_id}", token)
            assert s == 200, data
            status = data["data"]["status"]
            print(f"    ... task={task_id} status={status} progress={data['data']['progress']}")
            if status in ("success", "failed"):
                break
            time.sleep(1.5)
        assert status == "success", f"回测未成功: {status} {data.get('data', {}).get('error')}"
        print("[ok] 回测 success")

        # 5) 查询结果（N 区 / 全景K线策略指标数据源）
        s, data = _req("GET", f"/api/v1/backtest/results?strategy_id={sid}", token)
        assert s == 200 and data["data"], data
        result = data["data"][0]
        print(f"[ok] 结果: win_rate={result['win_rate']} 盈亏比={result['profit_loss_ratio']} "
              f"夏普={result['sharpe']} 年化={result['annual_return']} 最大回撤={result['max_drawdown']}")

        s, data = _req("GET", f"/api/v1/backtest/results/{result['id']}", token)
        assert s == 200, data
        mj = data["data"]["metrics_json"]
        print(f"[ok] 详情: 交易{mj['total_trades']}笔 累计买{mj['total_buys']}卖{mj['total_sells']} "
              f"总收益{mj['total_return']:.4f} 佣金{mj['commission_total']}")

        print("== 阶段四冒烟通过 ==")
        return 0
    finally:
        # 清理（直连 DB 删测试用户，级联删策略/任务/结果）
        from app.models.user import User
        from app.utils.db import get_session

        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
        finally:
            db.close()
        print("[ok] 清理测试数据")


if __name__ == "__main__":
    raise SystemExit(main())
