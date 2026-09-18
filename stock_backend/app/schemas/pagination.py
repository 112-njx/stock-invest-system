"""列表分页通用参数与响应信封（V0.3 · P1-6a / G09）。

约定：所有列表端点统一返回 `{items, total, page, size, total_pages}`；
对话消息因数据量随会话线性增长，改用游标分页 `{items, has_more, next_cursor}`。
"""

from typing import Any

from fastapi import Query

#: 每页默认条数
DEFAULT_PAGE_SIZE = 20
#: 每页最大条数（防止单次拉取过大响应体）
MAX_PAGE_SIZE = 100
#: 消息游标分页默认/最大条数
DEFAULT_MESSAGE_LIMIT = 50
MAX_MESSAGE_LIMIT = 200


class PageParams:
    """页码分页查询参数依赖：`page`（默认 1）、`size`（默认 20，最大 100）。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数，最大 100"),
    ) -> None:
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def total_pages(total: int, size: int) -> int:
    """总页数（空列表为 0，非 1）。"""
    if size <= 0:
        return 0
    return (total + size - 1) // size


def page_envelope(items: list[Any], total: int, page: int, size: int) -> dict:
    """统一分页信封：`{items, total, page, size, total_pages}`。"""
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": total_pages(total, size),
    }


def cursor_envelope(items: list[Any], has_more: bool, next_cursor: int | None) -> dict:
    """统一游标信封：`{items, has_more, next_cursor}`（items 按时间升序）。"""
    return {"items": items, "has_more": has_more, "next_cursor": next_cursor}
