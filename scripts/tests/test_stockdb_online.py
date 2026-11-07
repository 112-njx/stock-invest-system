import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('online', Path(__file__).parents[1] / 'stockdb_online.py')
online = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online)

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('STOCKDB_ONLINE_DIR', str(tmp_path))
    return tmp_path

def test_shared_cooldown_and_readable_archive(store, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_last_tick=lambda **kw: calls.append(kw) or [{'current': 11.8}]))
    payload = {'method': 'get_last_tick', 'code': '000001'}
    result = online.query('.', payload)
    archive = next(store.rglob('*.json'))
    assert archive.parent.name == '实时逐笔'
    assert json.loads(archive.read_text(encoding='utf-8'))['data'] == result['data']
    with pytest.raises(online.OnlineError) as exc:
        online.query('.', payload)
    assert exc.value.status == 429
    assert len(calls) == 1
    assert online.policy(60)['interval_seconds'] == 60
    assert online.policy()['retry_after'] > 30

def test_invalid_parameters_do_not_consume_quota(store):
    with pytest.raises(online.OnlineError):
        online.query('.', {'method': 'get_ticks', 'code': '000001'})
    assert online.policy()['retry_after'] == 0
    with pytest.raises(online.OnlineError):
        online.policy(1)

def test_empty_market_result_is_saved(store, monkeypatch):
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_billboard_list=lambda **kw: []))
    result = online.query('.', {'method': 'get_billboard_list', 'start_date': '2026-01-01', 'end_date': '2026-01-02'})
    assert result['data'] == []
    assert '全市场' in next(store.rglob('*.json')).name

def test_upstream_error_consumes_quota(store, monkeypatch):
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_last_tick=lambda **kw: {'error': 'unavailable'}))
    with pytest.raises(online.OnlineError) as exc:
        online.query('.', {'method': 'get_last_tick', 'code': '000001'})
    assert exc.value.status == 502
    assert online.policy()['retry_after'] > 0
    assert not list(store.rglob('*.json'))

def test_missing_financial_values_are_json_null(store, monkeypatch):
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_last_tick=lambda **kw: [{'missing': float('nan')}]))
    result = online.query('.', {'method': 'get_last_tick', 'code': '000001'})
    assert result['data'] == [{'missing': None}]
    assert json.loads(next(store.rglob('*.json')).read_text(encoding='utf-8'))['data'] == result['data']

def test_response_scope_mismatch_is_visible(store, monkeypatch):
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_money_flow=lambda **kw: [{'code': '603286', 'date': 20261030}]))
    result = online.query('.', {'method': 'get_money_flow', 'code': '000001', 'start_date': '2026-11-05', 'end_date': '2026-11-06'})
    assert len(result['warnings']) == 2
    assert result['data'][0]['code'] == '603286'
