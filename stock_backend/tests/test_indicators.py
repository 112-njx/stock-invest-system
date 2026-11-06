"""2.4 技术指标测试：MACD/KDJ 公式对照已知参考 + /api/v1/indicators API。"""

import datetime as dt
from datetime import UTC

import pandas as pd
import pytest
from app.models.kline import Kline1d
from app.models.symbol import Symbol
from app.services.indicators import get_indicator
from app.utils.db import get_session
from fastapi.testclient import TestClient


# ---- 单元：MACD 对照标准公式参考实现 ----
def _ema_ref(values: list[float], alpha: float) -> list[float]:
    out: list[float] = []
    prev = None
    for x in values:
        prev = x if prev is None else (1 - alpha) * prev + alpha * x
        out.append(prev)
    return out


def _macd_ref(close, fast=12, slow=26, signal=9):
    alpha_f, alpha_s, alpha_sig = 2 / (fast + 1), 2 / (slow + 1), 2 / (signal + 1)
    dif = [f - s for f, s in zip(_ema_ref(close, alpha_f), _ema_ref(close, alpha_s), strict=False)]
    dea = _ema_ref(dif, alpha_sig)
    hist = [2 * (d - e) for d, e in zip(dif, dea, strict=False)]
    return dif, dea, hist


def test_macd_matches_reference():
    close = [10, 11, 12, 11.5, 13, 14, 13.2, 15, 16, 14.5, 17, 18, 17.6, 19, 20, 19.2]
    df = pd.DataFrame({"close": close})
    out = get_indicator("macd").calculate(df)
    dif_r, dea_r, hist_r = _macd_ref(close)
    pd.testing.assert_series_equal(out["macd_dif"], pd.Series(dif_r, dtype="float64"), check_names=False, rtol=1e-9)
    pd.testing.assert_series_equal(out["macd_dea"], pd.Series(dea_r, dtype="float64"), check_names=False, rtol=1e-9)
    pd.testing.assert_series_equal(out["macd_hist"], pd.Series(hist_r, dtype="float64"), check_names=False, rtol=1e-9)


def test_macd_custom_params():
    close = [10.0, 11.0, 12.0]
    df = pd.DataFrame({"close": close})
    out = get_indicator("macd", {"fast": 2, "slow": 3, "signal": 2}).calculate(df)
    # 手算参考（alpha=2/(n+1)）：dif≈[0,0.1667,0.3056] dea≈[0,0.1111,0.2407] hist≈[0,0.1111,0.1296]
    assert out["macd_dif"].iloc[-1] == pytest.approx(0.3056, abs=1e-3)
    assert out["macd_dea"].iloc[-1] == pytest.approx(0.2407, abs=1e-3)
    assert out["macd_hist"].iloc[-1] == pytest.approx(0.1296, abs=1e-3)


# ---- 单元：KDJ 对照手算参考 ----
def test_kdj_hand_reference():
    df = pd.DataFrame({"high": [12, 13, 14, 15], "low": [8, 9, 10, 11], "close": [10, 11, 12, 13]})
    out = get_indicator("kdj", {"n": 3, "m1": 3, "m2": 3}).calculate(df)
    assert pd.isna(out["kdj_k"].iloc[0])  # 前 n-1 行为 NaN
    assert out["kdj_k"].iloc[2] == pytest.approx(55.5556, abs=1e-2)
    assert out["kdj_d"].iloc[2] == pytest.approx(51.8519, abs=1e-2)
    assert out["kdj_j"].iloc[2] == pytest.approx(62.963, abs=1e-2)
    assert out["kdj_k"].iloc[3] == pytest.approx(59.2593, abs=1e-2)
    assert out["kdj_d"].iloc[3] == pytest.approx(54.321, abs=1e-2)


def test_volume_amount_passthrough():
    df = pd.DataFrame({"volume": [100, 200, 300], "amount": [1e6, 2e6, 3e6], "close": [1, 2, 3]})
    for name in ("volume", "amount"):
        out = get_indicator(name).calculate(df.copy())
        assert list(out["volume"]) == [100, 200, 300]
        assert list(out["amount"]) == [1e6, 2e6, 3e6]
        if name == "volume":
            assert out["volume_ma5"].isna().all()


def test_unknown_indicator():
    with pytest.raises(ValueError):
        get_indicator("rsi")


def test_missing_column():
    with pytest.raises(ValueError):
        get_indicator("macd").calculate(pd.DataFrame({"high": [1, 2, 3]}))


# ---- API ----
@pytest.fixture()
def _indicator_data():
    db = get_session()
    sym = Symbol(code="666888", name="指标测试标的", type="stock", market="SSE")
    db.add(sym)
    db.commit()
    db.refresh(sym)
    close = 10.0
    bars = []
    for i in range(40):
        ts = dt.datetime(2026, 6, 1, tzinfo=UTC) + dt.timedelta(days=i)
        close = round(close + 0.3 + 0.2 * ((i % 5) - 2), 3)
        bars.append(
            Kline1d(
                symbol_id=sym.id,
                ts=ts,
                open=round(close - 0.1, 3),
                high=round(close + 0.5, 3),
                low=round(close - 0.5, 3),
                close=close,
                volume=1000 + i * 10,
                amount=1e6 + i * 1000,
            )
        )
    db.add_all(bars)
    db.commit()
    yield sym
    db.query(Kline1d).filter(Kline1d.symbol_id == sym.id).delete()
    db.query(Symbol).filter(Symbol.id == sym.id).delete()
    db.commit()
    db.close()


def test_indicators_api_columns(client: TestClient, _indicator_data):
    resp = client.get("/api/v1/indicators", params={"symbol": "666888", "period": "1d", "names": "macd,kdj"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 40
    row = data[-1]
    for col in ("ts", "open", "high", "low", "close", "volume", "amount"):
        assert col in row
    for col in ("macd_dif", "macd_dea", "macd_hist", "kdj_k", "kdj_d", "kdj_j"):
        assert col in row
    # 最后一根 K 线指标应已收敛为非空
    assert row["macd_dif"] is not None
    assert row["kdj_k"] is not None


def test_indicators_api_invalid_name(client: TestClient, _indicator_data):
    resp = client.get("/api/v1/indicators", params={"symbol": "666888", "names": "rsi"})
    assert resp.status_code == 400


def test_indicators_api_invalid_params_json(client: TestClient, _indicator_data):
    resp = client.get("/api/v1/indicators", params={"symbol": "666888", "names": "macd", "params": "{bad"})
    assert resp.status_code == 400


def test_indicators_api_cache_same_result(client: TestClient, _indicator_data):
    q = {"symbol": "666888", "period": "1d", "names": "macd,kdj"}
    r1 = client.get("/api/v1/indicators", params=q).json()["data"]
    r2 = client.get("/api/v1/indicators", params=q).json()["data"]
    assert r1 == r2


def test_sdk_native_values_and_volume_averages():
    from app.services.sdk_indicators import calculate
    rows = [dict(ts=str(i), high=float(i+2), low=float(i), close=float(i+1), volume=100+i, amount=1000) for i in range(16)]
    result = calculate(rows, ['macd', 'kdj', 'volume', 'amount'], {})
    assert result[1]['macd_dif'] == 0.08
    assert result[0]['kdj_k'] is None
    assert result[0]['volume_ma5'] is None
    assert result[-1]['macd_hist'] == 1.933
    assert result[-1]['kdj_k'] == 90.0
    assert result[-1]['volume_ma5'] == 113.0
    assert result[-1]['volume_ma10'] == 110.5
    custom = calculate(rows, ['macd'], {'macd': {'fast': 2, 'slow': 3, 'signal': 2}})
    assert custom[-1]['macd_dif'] != result[-1]['macd_dif']
    assert [r['ts'] for r in result] == [r['ts'] for r in rows]


def test_both_engines_preserve_paging_warmup(monkeypatch, _indicator_data):
    from app.services import indicator_service, indicator_policy
    policy = {'pandas_enabled': False, 'revision': 987654321}
    monkeypatch.setattr(indicator_policy, 'read', lambda: dict(policy))
    with get_session() as db:
        start = dt.datetime(2026, 6, 1, tzinfo=UTC)
        end = start + dt.timedelta(days=39)
        values = []
        for pandas_enabled in (False, True):
            policy['pandas_enabled'] = pandas_enabled
            complete = indicator_service.compute_indicators(db, str(_indicator_data.id), '1d', ['macd','volume'], start=start, end=end)
            page = indicator_service.compute_indicators(db, str(_indicator_data.id), '1d', ['macd','volume'], start=start+dt.timedelta(days=20), end=end)
            recent = indicator_service.compute_indicators(db, str(_indicator_data.id), '1d', ['macd','volume'], limit=5)
            assert page == complete[20:]
            assert recent == complete[-5:]
            values.append(complete)
        assert values[0][1]['macd_dif'] != values[1][1]['macd_dif']


def test_sdk_failure_does_not_invoke_pandas(client, monkeypatch, _indicator_data):
    from app.services import indicator_service, indicator_policy, sdk_indicators
    from app.core.exceptions import ApiError
    monkeypatch.setattr(indicator_policy, 'read', lambda: {'pandas_enabled':False,'revision':987654322})
    def failure(*args):
        raise ApiError(503, 50331, 'SDK unavailable')
    monkeypatch.setattr(sdk_indicators, 'calculate', failure)
    monkeypatch.setattr(indicator_service, '_bars_to_df', lambda *args: pytest.fail('Unexpected pandas fallback'))
    result = client.get('/api/v1/indicators', params={'symbol':str(_indicator_data.id),'names':'macd'})
    assert result.status_code == 503


def test_pandas_panels_survive_unavailable_sdk_ma(client, monkeypatch, _indicator_data):
    from app.services import indicator_service, indicator_policy, sdk_indicators
    from app.core.exceptions import ApiError
    monkeypatch.setattr(indicator_policy, 'read', lambda: {'pandas_enabled':True,'revision':987654323})
    monkeypatch.setattr(indicator_service, '_get_cache', lambda key: None)
    def unavailable(*args):
        raise ApiError(503, 50331, 'SDK unavailable')
    monkeypatch.setattr(sdk_indicators, 'calculate', unavailable)
    base = {'symbol':str(_indicator_data.id)}
    ma = client.get('/api/v1/indicators', params={**base,'names':'ma'})
    panels = client.get('/api/v1/indicators', params={**base,'names':'macd,kdj,volume,amount'})
    assert ma.status_code == 503
    assert panels.status_code == 200
    rows = panels.json()['data']
    assert len(rows) == 40
    for name in ('macd_hist', 'kdj_k', 'volume_ma5', 'volume_ma10', 'volume', 'amount'):
        assert rows[-1][name] is not None


@pytest.mark.parametrize('params', [{'macd':{'fast':0}}, {'kdj':{'n':True}}, {'macd':{'bad':12}}, {'macd':[]}])
def test_invalid_engine_parameters(client, _indicator_data, params):
    import json
    result = client.get('/api/v1/indicators', params={'symbol':str(_indicator_data.id),'names':'macd,kdj','params':json.dumps(params)})
    assert result.status_code == 400


def test_indicator_policy_requires_admin_and_notifies_views(client, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services import indicator_policy
    from app.main import app
    from app.api.deps import get_current_admin
    from app.ws import publisher
    assert client.get('/api/v1/admin/indicator-settings').status_code == 401
    assert client.put('/api/v1/admin/indicator-settings',json={'pandas_enabled':True}).status_code == 401
    original = indicator_policy.read()
    notify = Mock()
    monkeypatch.setattr(publisher, '_publish', notify)
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(is_admin=True)
    try:
        result = client.put('/api/v1/admin/indicator-settings',json={'pandas_enabled':not original['pandas_enabled']})
        assert result.status_code == 200
        assert result.json()['data']['revision'] > original['revision']
        assert result.json()['data']['pandas_enabled'] is not original['pandas_enabled']
        notify.assert_called_once_with({'type':'indicator_settings_changed'})
    finally:
        indicator_policy.save(original['pandas_enabled'])
        app.dependency_overrides.pop(get_current_admin,None)


def test_indicator_notification_broadcasts_without_symbol_id(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from app.api.v1.ws_market import _dispatch, manager
    notify = AsyncMock()
    monkeypatch.setattr(manager, 'broadcast_all', notify)
    asyncio.run(_dispatch(None, {'type':'indicator_settings_changed'}))
    notify.assert_awaited_once_with({'type':'indicator_settings_changed'})
