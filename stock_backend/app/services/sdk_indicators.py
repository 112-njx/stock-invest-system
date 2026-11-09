"""Compute indicators on exactly the bars chosen by the chart source policy."""
import json
from urllib.request import Request, urlopen
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.services.indicator_registry import MAX_REQUEST_BYTES


def calculate(rows, names, params, *, period=None):
    body = json.dumps(dict(rows=rows, names=names, params=params or {}, period=period), allow_nan=False).encode()
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("指标请求超过本地 SDK 容量上限，不能截断预热序列")
    request = Request(get_settings().STOCKDB_SDK_URL.rstrip('/') + '/indicators/calculate', data=body,
                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=55 if 'zhishu' in names else 45) as response:
            result = json.load(response)
        if not isinstance(result, list) or len(result) != len(rows) or any(
                r.get('ts') != b['ts'] for r, b in zip(result, rows)):
            raise ValueError('SDK returned mismatched indicator dates')
        return result
    except Exception as exc:
        raise ApiError(status_code=503, code=50331, msg='SDK 指标计算失败，请检查本地 7900 服务或在后台切换 pandas') from exc
