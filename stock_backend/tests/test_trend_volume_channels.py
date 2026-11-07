"""SDK-only batch 5–7 routing, history, validation and detail settings contracts."""
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from app.core.exceptions import ApiError
from app.services import indicator_registry as registry, indicator_service as service, indicator_policy, sdk_indicators

KEYS = 'dmi trix dfma mass vr cr emv brar obv mfi asi taq ktn xsii'.split()
CHANNELS = ['taq', 'ktn', 'xsii']
CUSTOM = {
    'dmi': {'m1': 9, 'm2': 3}, 'trix': {'m1': 7, 'm2': 9},
    'dfma': {'n1': 5, 'n2': 21, 'm': 6}, 'mass': {'n1': 5, 'n2': 12, 'm': 3},
    'vr': {'m1': 12}, 'cr': {'n': 9}, 'emv': {'n': 7, 'm': 3},
    'brar': {'m1': 12}, 'obv': {}, 'mfi': {'n': 7},
    'asi': {'m1': 12, 'm2': 5}, 'taq': {'n': 9},
    'ktn': {'n': 9, 'm': 5}, 'xsii': {'n': 104, 'm': 5},
}


@pytest.fixture
def bars(monkeypatch):
    values = [SimpleNamespace(ts=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
                              source='stockdb', open=19.5 + (i * 7) % 19 + (i % 3) * .2,
                              close=20. + (i * 7) % 19 + (i % 3) * .2,
                              high=22. + (i * 7) % 19 + (i % 3) * .2 + (i % 5) * .3,
                              low=19. + (i * 7) % 19, volume=1000 + (i * 13) % 127, amount=10000 + i)
              for i in range(180)]
    monkeypatch.setattr(service.market_service, 'resolve_symbol_id', lambda *a: 1)
    monkeypatch.setattr(service.kline_repo, 'get_bars', lambda *a, **k: values)
    monkeypatch.setattr(service, '_get_cache', lambda *a: None)
    monkeypatch.setattr(service, '_set_cache', lambda *a: None)
    monkeypatch.setattr(service, '_cache_key', lambda *a, **k: 'isolated-trend-volume-channels')
    return values


@pytest.mark.parametrize('period', ['1d', '1w', '1mon', '15m'])
@pytest.mark.parametrize('pandas_enabled', [False, True])
def test_sdk_routing_paging_latest_and_active_bar_update(monkeypatch, bars, period, pandas_enabled):
    monkeypatch.setattr(indicator_policy, 'read', lambda: {'pandas_enabled': pandas_enabled, 'revision': 1})
    monkeypatch.setattr(service, '_bars_to_df', lambda *a: pytest.fail('All batch 5–7 indicators must use SDK'))
    full = service.compute_indicators(None, '1', period, KEYS, CUSTOM, limit=180)
    page = service.compute_indicators(None, '1', period, KEYS, CUSTOM, start=bars[100].ts, end=bars[-1].ts)
    recent = service.compute_indicators(None, '1', period, KEYS, CUSTOM, limit=5)
    assert page == full[100:]
    assert recent == full[-5:]
    for key in KEYS:
        d = registry.REGISTRY[key]
        assert d['placement'] == ('main' if key in CHANNELS else 'panel')
        assert d['engines'] == ['sdk']
        assert all(full[-1][field] is not None for field in d['native_outputs'])
    bars[-1].close += 5
    bars[-1].high += 5
    bars[-1].volume += 1000
    updated = service.compute_indicators(None, '1', period, KEYS, CUSTOM, limit=5)
    for key in KEYS:
        assert any(updated[-1][f] != recent[-1][f] for f in registry.REGISTRY[key]['native_outputs']), key


def test_empty_and_short_history_preserve_sdk_nulls(monkeypatch, bars):
    monkeypatch.setattr(indicator_policy, 'read', lambda: {'pandas_enabled': False, 'revision': 1})
    del bars[1:]
    result = service.compute_indicators(None, '1', '1d', KEYS)
    from app.utils.market_cache import kline_bar_to_dict
    assert result == sdk_indicators.calculate([kline_bar_to_dict(bars[0])], KEYS, {})
    assert result[0]['mass'] is None
    assert result[0]['taq_up'] is None
    bars.clear()
    monkeypatch.setattr(sdk_indicators, 'calculate', lambda *a: pytest.fail('Empty history must skip SDK'))
    assert service.compute_indicators(None, '1', '1d', KEYS) == []


@pytest.mark.parametrize('key,param', [(k, p['key']) for k in KEYS for p in registry.REGISTRY[k]['parameters']])
@pytest.mark.parametrize('invalid', [0, 10001, True, 1.5, '12'])
def test_api_parameter_rejection(client, key, param, invalid):
    response = client.get('/api/v1/indicators', params={
        'symbol': '300502', 'names': key, 'params': json.dumps({key: {param: invalid}})})
    assert response.status_code == 400


def test_panel_and_channel_failure_isolation(client, monkeypatch, bars):
    monkeypatch.setattr(indicator_policy, 'read', lambda: {'pandas_enabled': True, 'revision': 1})
    original = sdk_indicators.calculate
    def failing(rows, names, params):
        if names in (['dmi'], ['taq']):
            raise ApiError(503, 50331, 'SDK unavailable')
        return original(rows, names, params)
    monkeypatch.setattr(sdk_indicators, 'calculate', failing)
    for key in KEYS:
        response = client.get('/api/v1/indicators', params={'symbol': '1', 'names': key})
        assert response.status_code == (503 if key in ['dmi', 'taq'] else 200)
