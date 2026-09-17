"""通知域请求/响应模型（统一由 {code, msg, data} 包裹）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    content: str | None = None
    is_read: bool
    created_at: datetime
    read_at: datetime | None = None


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int


class UnreadCountOut(BaseModel):
    unread: int


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    type: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None


class AnnouncementIn(BaseModel):
    """管理员发布公告。"""

    title: str = Field(min_length=1, max_length=255, description="公告标题")
    content: str = Field(min_length=1, description="公告内容")
    type: str = Field("info", pattern=r"^(info|warning|maintenance)$", description="info/warning/maintenance")
    expires_at: datetime | None = Field(None, description="过期时间（NULL=永不过期）")
    notify_users: bool = Field(True, description="是否向全部用户分发站内通知")
