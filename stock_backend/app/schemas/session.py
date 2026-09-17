"""G19 会话域 schema：SessionOut / AuthOut。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionOut(BaseModel):
    """活跃设备列表项。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_agent: str | None = None
    ip_address: str | None = None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False  # 标记当前设备（运行时由 service 层注入）


class AuthOut(BaseModel):
    """登录/注册响应（G19：access_token 在 body，refresh_token 在 HttpOnly Cookie）。"""

    token: str  # access token（前端存内存，G19 过渡期保留 Bearer 兼容）
    user: dict  # UserOut 序列化结果
