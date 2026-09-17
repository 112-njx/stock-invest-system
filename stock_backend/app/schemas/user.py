"""用户域响应模型：鉴权、关注列表、支撑/压力位（统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.validators import HttpUrlTextOptional, SafeTextOptional


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$", description="用户名")
    password: str = Field(min_length=6, max_length=128, description="密码（明文，服务端 bcrypt 哈希）")
    email: str = Field(max_length=128, description="邮箱（必填，用于账号验证和密码重置）")
    nickname: SafeTextOptional = Field(None, max_length=64)


class LoginIn(BaseModel):
    # G30：补长度上限，避免超长输入打到 bcrypt（CPU 消耗）与日志
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=128, description="注册邮箱")


class ResetPasswordIn(BaseModel):
    token: str = Field(max_length=512, description="重置密码 token（从邮件链接获取）")
    new_password: str = Field(min_length=6, max_length=128, description="新密码")


class ChangePasswordIn(BaseModel):
    """G33：已登录用户修改密码。"""

    old_password: str = Field(max_length=128, description="当前密码（校验身份）")
    new_password: str = Field(min_length=6, max_length=128, description="新密码")


class ChangeEmailIn(BaseModel):
    """G33：已登录用户修改邮箱（新邮箱需重新验证）。"""

    password: str = Field(max_length=128, description="当前密码（校验身份）")
    new_email: str = Field(max_length=128, description="新邮箱")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    email_verified: bool = False
    nickname: str | None = None
    avatar_url: str | None = None
    created_at: datetime


class TokenOut(BaseModel):
    token: str
    user: UserOut


class UserUpdateIn(BaseModel):
    nickname: SafeTextOptional = Field(None, max_length=64)
    # G30：头像地址仅允许 http/https/站内路径，拒绝 javascript:/data: 等可执行协议
    avatar_url: HttpUrlTextOptional = Field(None, max_length=255)


# ---- 重点关注股票 ----
class WatchlistAddIn(BaseModel):
    symbol: str = Field(..., max_length=32, description="标的代码（或 symbol_id）")


class WatchlistOut(BaseModel):
    """关注列表行：合并实时快照（代码/名称/最新价/涨跌幅）+ 同步状态。"""

    id: int
    symbol_id: int
    code: str
    name: str
    type: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    updated_at: datetime | None = None
    sync_status: str = "pending"  # pending/syncing/done/failed
    last_synced_at: datetime | None = None
    created_at: datetime


# ---- 支撑/压力位 ----
class SupportResistanceIn(BaseModel):
    symbol: str = Field(..., max_length=32, description="标的代码（或 symbol_id）")
    type: Literal["support", "pressure"] = Field(..., description="support=支撑位 / pressure=压力位")
    price: float = Field(..., description="价位")
    note: SafeTextOptional = Field(None, max_length=255)


class SupportResistanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_id: int
    type: str
    price: float
    note: str | None = None
    created_at: datetime
