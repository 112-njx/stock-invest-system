"""Momentum panels: SDK routing, pagination, parameter validation and error isolation."""
from datetime import UTC,datetime,timedelta
from types import SimpleNamespace
import json
import pytest
from app.services import indicator_registry as registry,indicator_service as service,indicator_policy,sdk_indicators
from app.core.exceptions import ApiError
KEYS=['bias','psy','dpo','mtm','roc']
CUSTOM={'bias':{'l1':3,'l2':9,'l3':18},'psy':{'n':9,'m':3},'dpo':{'m1':12,'m2':6,'m3':3},'mtm':{'n':7,'m':3},'roc':{'n':7,'m':3}}
@pytest.fixture
def bars(monkeypatch):
    values=[SimpleNamespace(ts=datetime(2025,1,1,tzinfo=UTC)+timedelta(days=i),source='stockdb',open=10,high=30,low=9,close=10.+(i*7)%19+(i%3)*.2,volume=100+i,amount=1000+i) for i in range(100)]
    monkeypatch.setattr(service.market_service,'resolve_symbol_id',lambda *a:1)
    monkeypatch.setattr(service.kline_repo,'get_bars',lambda *a,**k:values)
    monkeypatch.setattr(service,'_get_cache',lambda *a:None)
    monkeypatch.setattr(service,'_set_cache',lambda *a:None)
    monkeypatch.setattr(service,'_cache_key',lambda *a,**k:'isolated-momentum-panels')
    return values
@pytest.mark.parametrize('period',['1d','1w','1mon','15m'])
@pytest.mark.parametrize('pandas_enabled',[False,True])
def test_native_panels_warmup_paging_and_engine(monkeypatch,bars,period,pandas_enabled):
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':pandas_enabled,'revision':1})
    monkeypatch.setattr(service,'_bars_to_df',lambda *a:pytest.fail('Momentum panels must use SDK'))
    full=service.compute_indicators(None,'1',period,KEYS,CUSTOM,limit=100)
    page=service.compute_indicators(None,'1',period,KEYS,CUSTOM,start=bars[60].ts,end=bars[-1].ts)
    recent=service.compute_indicators(None,'1',period,KEYS,CUSTOM,limit=5)
    assert page==full[60:]
    assert recent==full[-5:]
    assert len(full)==100
    for key in KEYS:
        d=registry.REGISTRY[key]
        assert d['placement']=='panel' and d['engines']==['sdk']
        for field in d['native_outputs']:
            assert full[0][field] is None
            assert full[-1][field] is not None

PARAMETERS=[(key,p['key']) for key in KEYS for p in registry.REGISTRY[key]['parameters']]
@pytest.mark.parametrize('key,param',PARAMETERS)
@pytest.mark.parametrize('invalid',[0,10001,True,1.5,'12'])
def test_api_rejects_invalid_parameters(client,key,param,invalid):
    response=client.get('/api/v1/indicators',params={'symbol':'300502','names':key,'params':json.dumps({key:{param:invalid}})})
    assert response.status_code==400

def test_one_failure_does_not_block_other_indicator_requests(client,monkeypatch,bars):
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':True,'revision':1})
    original=sdk_indicators.calculate
    def fail_bias(rows,names,params):
        if names==['bias']:raise ApiError(503,50331,'BIAS unavailable')
        return original(rows,names,params)
    monkeypatch.setattr(sdk_indicators,'calculate',fail_bias)
    assert client.get('/api/v1/indicators',params={'symbol':'1','names':'bias'}).status_code==503
    for key in ['psy','dpo','mtm','roc']:
        assert client.get('/api/v1/indicators',params={'symbol':'1','names':key}).status_code==200
