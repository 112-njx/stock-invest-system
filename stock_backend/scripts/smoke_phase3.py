"""阶段三冒烟测试：会话/策略/定制Agent/聊天（SSE 降级）全流程。

用法：`uvicorn app.main:app` 启动后运行 `python scripts/smoke_phase3.py`。
- 自动注册临时用户、清理测试数据。
- 未配置 DEEPSEEK_API_KEY 时，聊天走降级文案（验证链路通）。
- 配置了 Key 时，聊天会真实调用 DeepSeek（可观察 SSE 流式）。
"""

import json
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
_PREFIX = "smoke3_"


def _req(method: str, path: str, token: str | None = None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.request(method, BASE + path, headers=headers, timeout=60, **kw)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    return r.status_code, body


def main() -> int:
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    print(f"== 阶段三冒烟：用户 {uname} ==")

    # 1) 注册
    s, data = _req("POST", "/api/v1/auth/register", json={"username": uname, "password": "pass123456"})
    assert s == 200 and data["code"] == 0, data
    token = data["data"]["token"]
    print("[ok] 注册")

    # 2) 会话
    s, data = _req("POST", "/api/v1/conversations", token, json={"title": "冒烟会话"})
    assert s == 200, data
    conv_id = data["data"]["id"]
    s, data = _req("POST", f"/api/v1/conversations/{conv_id}/messages", token,
                   json={"role": "user", "content": "你好"})
    assert s == 200, data
    print(f"[ok] 会话创建+消息 conv_id={conv_id}")

    # 3) 策略 CRUD
    s, data = _req("POST", "/api/v1/strategies", token,
                   json={"title": "冒烟策略", "code": "def on_bar(bar, context):\n    pass", "status": "draft"})
    assert s == 200, data
    sid = data["data"]["id"]
    s, data = _req("GET", "/api/v1/strategies", token)
    assert any(x["id"] == sid for x in data["data"]), data
    print(f"[ok] 策略保存+列表 strategy_id={sid}")

    # 4) 定制 Agent（从风控模板创建）
    s, data = _req("POST", "/api/v1/agents", token, json={"name": "冒烟风控", "template": "risk_control"})
    assert s == 200 and "风控" in data["data"]["system_prompt"], data
    aid = data["data"]["id"]
    print(f"[ok] 定制 Agent（模板创建） agent_id={aid}")

    # 5) 聊天（SSE）—— 未配置 Key 时验证降级链路
    with httpx.stream("POST", BASE + "/api/v1/chat", headers={"Authorization": f"Bearer {token}"},
                      json={"conversation_id": conv_id, "content": "帮我诊断当前趋势", "run_type": "diagnose"},
                      timeout=60) as resp:
        assert resp.status_code == 200
        events = 0
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                events += 1
                print(f"   SSE[{ev.get('type')}]: {str(ev.get('content', ''))[:40]} {ev.get('node', '')}")
    print(f"[ok] 聊天 SSE 事件数={events}（未配置 DeepSeek Key 时为降级文案）")

    # 6) 清理（直连 DB 删测试用户，级联删其余）
    _req("DELETE", f"/api/v1/agents/{aid}", token)
    _req("DELETE", f"/api/v1/strategies/{sid}", token)
    _req("DELETE", f"/api/v1/conversations/{conv_id}", token)
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
    print("== 阶段三冒烟全部通过 ==")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print("断言失败：", e)
        sys.exit(1)
