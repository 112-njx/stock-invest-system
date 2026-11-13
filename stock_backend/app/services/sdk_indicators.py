"""Compute indicators on exactly the bars chosen by the chart source policy."""
import json
from urllib.request import Request, urlopen
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.services.indicator_registry import FORECAST_FEATURES, MAX_REQUEST_BYTES


def calculate(rows, names, params, *, period=None, return_checkpoint=False, checkpoint=None):
    payload = dict(rows=rows, names=names, params=params or {}, period=period)
    if return_checkpoint:
        payload.update(return_checkpoint=True, checkpoint=checkpoint)
    body = json.dumps(payload, allow_nan=False).encode()
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("指标请求超过本地 SDK 容量上限，不能截断预热序列")
    request = Request(get_settings().STOCKDB_SDK_URL.rstrip('/') + '/indicators/calculate', data=body,
                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=55 if 'zhishu' in names else 45) as response:
            result = json.load(response)
        aligned = result
        if return_checkpoint:
            if not isinstance(result, dict) or not isinstance(result.get('checkpoint'), str):
                raise ValueError('SDK did not return an indicator checkpoint')
            aligned = result.get('rows')
        if not isinstance(aligned, list) or len(aligned) != len(rows) or any(
                r.get('ts') != b['ts'] for r, b in zip(aligned, rows)):
            raise ValueError('SDK returned mismatched indicator dates')
        return result
    except Exception as exc:
        if FORECAST_FEATURES in names:
            raise ApiError(status_code=503, code=50331, msg='走势特征计算暂不可用，请稍后重试') from exc
        raise ApiError(status_code=503, code=50331, msg='SDK 指标计算失败，请检查本地 7900 服务或在后台切换 pandas') from exc
