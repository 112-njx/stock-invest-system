"""SDK indicator values and HTTP contracts."""

import datetime as dt
from datetime import UTC

import pytest
from app.models.kline import Kline1d
from app.models.symbol import Symbol
from app.utils.db import get_session
from fastapi.testclient import TestClient


@pytest.fixture()
def _indicator_data():
    db = get_session()
    sym = Symbol(code="666888", name="指标测试标的", type="index", market="SSE")
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
    resp = client.get("/api/v1/indicators", params={"symbol": "666888", "names": "unknown_indicator"})
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


def test_sdk_preserves_paging_warmup(_indicator_data):
    from app.services import indicator_service

    with get_session() as db:
        start = dt.datetime(2026, 6, 1, tzinfo=UTC)
        end = start + dt.timedelta(days=39)
        args = (db, str(_indicator_data.id), '1d', ['macd', 'volume'])
        complete = indicator_service.compute_indicators(*args, start=start, end=end)
        page = indicator_service.compute_indicators(*args, start=start + dt.timedelta(days=20), end=end)
        recent = indicator_service.compute_indicators(*args, limit=5)
        assert page == complete[20:]
        assert recent == complete[-5:]


@pytest.mark.parametrize('names', ['ma', 'macd,kdj,volume,amount'])
def test_sdk_failure_returns_unavailable(client, monkeypatch, _indicator_data, names):
    from app.services import indicator_service, sdk_indicators
    from app.core.exceptions import ApiError

    def unavailable(*args):
        raise ApiError(503, 50331, 'SDK unavailable')

    monkeypatch.setattr(indicator_service, '_get_cache', lambda key: None)
    monkeypatch.setattr(sdk_indicators, 'calculate', unavailable)
    result = client.get('/api/v1/indicators', params={'symbol':str(_indicator_data.id), 'names':names})
    assert result.status_code == 503


@pytest.mark.parametrize('params', [{'macd':{'fast':0}}, {'kdj':{'n':True}}, {'macd':{'bad':12}}, {'macd':[]}])
def test_invalid_engine_parameters(client, _indicator_data, params):
    import json
    result = client.get('/api/v1/indicators', params={'symbol':str(_indicator_data.id),'names':'macd,kdj','params':json.dumps(params)})
    assert result.status_code == 400


def test_indicator_engine_switch_is_retired(client):
    assert client.get('/api/v1/admin/indicator-settings').status_code == 404
    assert client.put('/api/v1/admin/indicator-settings', json={}).status_code == 404
