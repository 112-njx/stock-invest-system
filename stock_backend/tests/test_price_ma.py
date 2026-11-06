"""MA dispatch, history warmup and active-candle cache regression checks."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import indicator_policy, indicator_service, sdk_indicators


@pytest.mark.parametrize('pandas_enabled', [True, False])
def test_price_ma_uses_sdk_and_crops_after_warmup(monkeypatch, pandas_enabled):
    first = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [SimpleNamespace(ts=first + timedelta(days=i), open=i+1, high=i+2,
                            low=i+1, close=i+1, volume=100, amount=1000,
                            source='stockdb') for i in range(60)]
    monkeypatch.setattr(indicator_service.market_service, 'resolve_symbol_id', lambda *a: 1)
    monkeypatch.setattr(indicator_service.kline_repo, 'get_bars', lambda *a, **k: bars)
    monkeypatch.setattr(indicator_policy, 'read', lambda: dict(pandas_enabled=pandas_enabled, revision=1))
    monkeypatch.setattr(indicator_service, '_cache_key', lambda *a, **k: 'test')
    monkeypatch.setattr(indicator_service, '_get_cache', lambda key: None)
    keys = []
    monkeypatch.setattr(indicator_service, '_set_cache', lambda key, rows: keys.append(key))
    calls = []

    def sdk(rows, names, params):
        calls.append((rows, names))
        return [{**r, 'ma30': None if i < 29 else sum(b.close for b in bars[i-29:i+1])/30}
                for i, r in enumerate(rows)]

    monkeypatch.setattr(sdk_indicators, 'calculate', sdk)
    result = indicator_service.compute_indicators(None, '1', '1d', ['ma'],
                                                  start=bars[40].ts, end=bars[-1].ts)
    assert len(calls[0][0]) == 60
    assert calls[0][1] == ['ma']
    assert len(result) == 20
    assert result[0]['ma30'] == 26.5
    bars[-1].close += 2
    indicator_service.compute_indicators(None, '1', '1d', ['ma'], start=bars[40].ts, end=bars[-1].ts)
    assert keys[0] != keys[1]
