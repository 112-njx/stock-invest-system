import importlib.util
import json
import sys
import types
import sqlite3
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

spec = importlib.util.spec_from_file_location('online', Path(__file__).parents[1] / 'stockdb_online.py')
online = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online)
from stockdb_online_catalog import CATALOG, BY_ID, REPORTS
from stockdb_online_requests import invoke

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

@pytest.mark.parametrize('count', [0, '', None, 1001])
@pytest.mark.parametrize('method', ['get_fundamentals', 'get_billboard_list', 'get_locked_shares', 'get_money_flow', 'get_mtss'])
def test_non_tick_queries_ignore_hidden_count(method, count):
    payload = {'method': method, 'code': '000001', 'count': count,
               'report': 'cash_flow', 'quarter': '2024q4',
               'start_date': '2026-11-05', 'end_date': '2026-11-06'}
    _, _, args = online.parameters(payload)
    assert 'count' not in args

@pytest.mark.parametrize('method', ['get_last_tick', 'get_ticks'])
@pytest.mark.parametrize('count', [0, '', None, 1001])
def test_tick_queries_still_reject_invalid_count(method, count):
    with pytest.raises(online.OnlineError, match='条数'):
        online.parameters({'method': method, 'code': '000001', 'count': count,
                           'end_dt': '2026-11-06 15:00:00'})

@pytest.mark.parametrize('old_interval,expected', [(30, 40), (39, 40), (40, 40), (60, 60), (86400, 86400)])
def test_migrate_policy_without_resetting_last_request(store, old_interval, expected):
    _, db = online.database()
    db.execute('UPDATE quota SET interval=?, last=123456 WHERE id=1', (old_interval,))
    db.commit(); db.close()
    assert online.policy()['interval_seconds'] == expected
    with sqlite3.connect(store / '请求频率配置.sqlite') as db:
        assert db.execute('SELECT last FROM quota').fetchone()[0] == 123456

def test_new_policy_default_and_floor(store):
    assert online.policy()['interval_seconds'] == 40
    for interval in (0, 30, 39, 40.0, True):
        with pytest.raises(online.OnlineError): online.policy(interval)
    assert online.policy(41)['interval_seconds'] == 41

class Expression:
    def __init__(self, path, calls): self.path, self.calls = path, calls
    def __getattr__(self, name): return Expression(self.path + '.' + name, self.calls)
    def __call__(self, *args, **kwargs):
        self.calls.append((self.path, args, kwargs))
        if self.path.endswith('run_query') or self.path.startswith('sdk.get_'):
            return [{'code': '000001', 'value': 42}]
        return self
    def __eq__(self, other): self.calls.append((self.path + '.eq', (other,), {})); return self
    def __ne__(self, other): return self
    def __lt__(self, other): return self
    def __le__(self, other): return self
    def __gt__(self, other): return self
    def __ge__(self, other): return self

@pytest.mark.parametrize('entry', CATALOG, ids=lambda entry: entry['id'])
def test_every_catalog_entry_builds_and_dispatches_one_query(entry):
    calls = []
    sdk = Expression('sdk', calls)
    payload = {'method': entry['id'], 'code': '000001', 'count': 2,
               'report': 'indicator', 'quarter': '2024q4', 'symbol': 'IF',
               'start_date': '2026-11-01', 'end_date': '2026-11-06', 'date': '2026-11-01',
               'end_dt': '2026-11-06 15:00:00', 'codes': '000001,600000',
               'factors': 'pe_ratio,pb_ratio', 'info': 'unit_net_value'}
    if entry['kind'] == 'table':
        field = next(iter(entry['fields']), 'id')
        payload.update(filters=[{'field': field, 'op': '==', 'value': '000001'}],
                       fields=[field], order_field=field, order_direction='desc', limit=50)
    method, code, args = online.parameters(payload)
    result = invoke(sdk, method, code, args)
    assert result == [{'code': '000001', 'value': 42}]
    executions = [call for call in calls if call[0].endswith('run_query') or call[0].startswith('sdk.get_')]
    assert len(executions) == 1
    if entry['kind'] == 'table':
        root, table = entry['id'].split('.')
        assert executions[0][0] == f'sdk.{root}.run_query'
        assert any(call[0].endswith('.limit') and call[1] == (50,) for call in calls)
        assert any(call[0].endswith('.eq') and call[1] == ('000001',) for call in calls)
    elif method == 'get_fundamentals_continuously':
        assert executions[0][2] == {'end_date': '2026-11-06', 'count': 2}
    elif method == 'get_factor_values':
        assert executions[0][2]['securities'] == ['000001', '600000']

def test_catalog_scope():
    assert len(CATALOG) == len(BY_ID) == 83
    assert len([item for item in CATALOG if item['kind'] == 'table']) == 68
    assert len({item['group'] for item in CATALOG}) == 21
    assert {item['id'] for item in CATALOG if item['group'] == '融资融券'} == {'get_mtss', 'get_margincash_stocks', 'get_marginsec_stocks'}
    assert 'indicator' in REPORTS

@pytest.mark.parametrize('payload', [
    {'method': 'finance.__dict__'},
    {'method': 'finance.STK_FIN_FORCAST', 'fields': ['__class__']},
    {'method': 'finance.STK_FIN_FORCAST', 'filters': [{'field': 'code', 'op': 'exec', 'value': '000001'}]},
    {'method': 'finance.STK_FIN_FORCAST', 'order_field': 'another.code'},
    {'method': 'finance.STK_FIN_FORCAST', 'limit': 5001},
    {'method': 'finance.CCTV_NEWS', 'fields': ['__dict__']},
    {'method': 'get_extras', 'code': '000001', 'info': 'is_st', 'start_date': '2026-11-01', 'end_date': '2026-11-06'},
])
def test_invalid_catalog_queries_do_not_consume_quota(store, payload):
    with pytest.raises(online.OnlineError): online.query('.', payload)
    assert online.policy()['retry_after'] == 0

def test_contract_string_is_success_and_archived(store, monkeypatch):
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_dominant_future=lambda **kw: 'IF2611.CCFX'))
    result = online.query('.', {'method': 'get_dominant_future', 'symbol': 'IF'})
    assert result['data'] == 'IF2611.CCFX'
    archive = next(store.rglob('*.json'))
    assert archive.parent.name == '期货主力合约'
    assert archive.parent.parent.name == '期货'

def test_sdk_error_is_reported_and_cooled_down(store, monkeypatch):
    def failing(**kwargs): raise RuntimeError('参数不支持')
    monkeypatch.setitem(sys.modules, 'stock_sdk', types.SimpleNamespace(get_dominant_future=failing))
    with pytest.raises(online.OnlineError, match='参数不支持'):
        online.query('.', {'method': 'get_dominant_future', 'symbol': 'IF'})
    assert online.policy()['retry_after'] >= 39

def test_nested_frames_and_duplicate_index_names():
    import pandas as pd
    frame = pd.DataFrame([{'code': '000001', 'score': float('nan')}])
    frame.index.name = 'code'
    result = online.normalize({'factor': frame})
    assert result == {'factor': [{'原始_code': 0, 'code': '000001', 'score': None}]}

@pytest.mark.parametrize('table,field', [('finance.STK_AH_PRICE_COMP', 'id'), ('finance.STK_AUDIT_OPINION', 'code'), ('finance.STK_FIN_FORCAST', 'id')])
def test_real_fields_missing_from_documentation_can_be_used(table, field):
    payload = {'method': table, 'filters': [{'field': field, 'op': '>', 'value': 100}],
               'fields': [field], 'order_field': field, 'order_direction': 'asc'}
    method, code, args = online.parameters(payload)
    assert args['fields'] == [field]
    calls = []
    invoke(Expression('sdk', calls), method, code, args)
    assert any(call[0].endswith(f'.{field}.asc') for call in calls)
    assert sum(call[0].endswith('run_query') for call in calls) == 1

@pytest.mark.parametrize('field', ['__class__', '_private', 'other.code', 'id desc', 'id;drop table', 'code()', 'id--', '1field', 'a' * 81])
@pytest.mark.parametrize('slot', ['fields', 'filters', 'order_field'])
def test_extended_fields_still_reject_paths_and_expressions(store, field, slot):
    payload = {'method': 'finance.STK_FIN_FORCAST'}
    payload[slot] = [field] if slot == 'fields' else [{'field': field, 'op': '==', 'value': 'test'}] if slot == 'filters' else field
    with pytest.raises(online.OnlineError, match='字段名'):
        online.query('.', payload)
    assert online.policy()['retry_after'] == 0
