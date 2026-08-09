"""技术指标 API：服务端计算 MACD/KDJ/成交量/成交额（前端只渲染，不计算）。"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import ApiError
from app.core.response import ok
from app.services import indicator_service

router = APIRouter(prefix="/api/v1", tags=["indicators"])


@router.get("/indicators")
def get_indicators(
    symbol: str = Query(..., description="标的代码（或 symbol_id）"),
    period: str = Query("1d", pattern="^(15m|1d|1w|1mon)$"),
    names: str = Query("macd,kdj,volume,amount", description="逗号分隔的指标名"),
    start: datetime | None = Query(None, description="开始时间（UTC）"),
    end: datetime | None = Query(None, description="结束时间（UTC）"),
    limit: int = Query(1000, ge=1, le=5000),
    params: str | None = Query(None, description=r'JSON 指标参数，如 {"macd":{"fast":12},"kdj":{"n":9}}'),
    db: Session = Depends(get_db),
) -> dict:
    try:
        name_list = [n.strip().lower() for n in names.split(",") if n.strip()]
        params_dict = json.loads(params) if params else None
        if params_dict is not None and not isinstance(params_dict, dict):
            raise ValueError("params 必须是 JSON 对象")
        rows = indicator_service.compute_indicators(db, symbol, period, name_list, params_dict, start, end, limit=limit)
    except json.JSONDecodeError as exc:
        raise ApiError(status_code=400, code=40003, msg="params 不是合法 JSON") from exc
    except ValueError as exc:
        raise ApiError(status_code=400, code=40004, msg=str(exc)) from exc
    return ok(data=rows)
