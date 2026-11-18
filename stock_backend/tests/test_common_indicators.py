"""Common panels: native routing, all periods, warmup, validation and failure isolation."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import json
import pytest
from app.services import indicator_registry as registry, indicator_service as service, sdk_indicators
from app.core.exceptions import ApiError

DB = SimpleNamespace(get=lambda *_: None)

KEYS=['rsi','wr','cci','atr']
CUSTOM={'rsi':{'n':7},'wr':{'n':14,'n1':5},'cci':{'n':9},'atr':{'n':6}}

@pytest.fixture
def bars(monkeypatch):
    rows=[SimpleNamespace(ts=datetime(2025,1,1,tzinfo=UTC)+timedelta(days=i),source='stockdb',open=10+(i*7)%19,close=10.+(i*7)%19+(i%3)*.2,high=12.+(i*7)%19+(i%3)*.2,low=9.+(i*7)%19+(i%3)*.2,volume=100+i,amount=1000+i) for i in range(80)]
    monkeypatch.setattr(service.market_service,'resolve_symbol_id',lambda *a:1)
    monkeypatch.setattr(service.kline_repo,'get_bars',lambda *a,**kw:rows)
    monkeypatch.setattr(service,'_get_cache',lambda *a:None)
    monkeypatch.setattr(service,'_set_cache',lambda *a:None)
    monkeypatch.setattr(service,'_cache_key',lambda *a,**kw:'isolated-common-indicators')
    return rows

@pytest.mark.parametrize('period',['1d','1w','1mon','15m'])
def test_real_sdk_routing_and_paging(monkeypatch,bars,period):
    full=service.compute_indicators(DB,'1',period,KEYS,CUSTOM,limit=80)
    page=service.compute_indicators(DB,'1',period,KEYS,CUSTOM,start=bars[40].ts,end=bars[-1].ts)
    recent=service.compute_indicators(DB,'1',period,KEYS,CUSTOM,limit=5)
    assert len(full)==80
    assert page==full[40:]
    assert recent==full[-5:]
    for name in KEYS:
        for field in registry.REGISTRY[name]['native_outputs']:
            assert field in full[0] and full[0][field] is None
            assert full[-1][field] is not None

@pytest.mark.parametrize('name',KEYS)
@pytest.mark.parametrize('value',[0,10001,True,1.5,'14'])
def test_api_rejects_invalid_period(client,name,value):
    response=client.get('/api/v1/indicators',params={'symbol':'300502','names':name,'params':json.dumps({name:{'n':value}})})
    assert response.status_code==400

def test_new_panel_failure_keeps_other_queries_available(client,monkeypatch,bars):
    calculate=sdk_indicators.calculate
    def fail_rsi(rows,names,params):
        if names==['rsi']: raise ApiError(503,50331,'RSI unavailable')
        return calculate(rows,names,params)
    monkeypatch.setattr(sdk_indicators,'calculate',fail_rsi)
    assert client.get('/api/v1/indicators',params={'symbol':'1','names':'rsi'}).status_code==503
    for key in ['wr','cci','atr']:
        assert client.get('/api/v1/indicators',params={'symbol':'1','names':key}).status_code==200
