"""Main overlay routing, history alignment and public parameter validation."""
import json
from datetime import UTC,datetime,timedelta
from types import SimpleNamespace
import pytest
from app.services import indicator_service as service,indicator_policy,indicator_registry as registry
KEYS=['boll','ema','expma','bbi','wma','sma','dma']
CUSTOM={'boll':{'n':10,'p':2.5},'ema':{'n':9},'expma':{'n1':7,'n2':21},'bbi':{'m1':2,'m2':5,'m3':9,'m4':15},'wma':{'n':9},'sma':{'n':9,'m':2},'dma':{'a':.25}}
@pytest.fixture
def bars(monkeypatch):
    values=[SimpleNamespace(ts=datetime(2025,1,1,tzinfo=UTC)+timedelta(days=i),source='stockdb',open=10,high=30,low=9,close=10.+(i*7)%19+(i%3)*.2,volume=100+i,amount=1000+i) for i in range(80)]
    monkeypatch.setattr(service.market_service,'resolve_symbol_id',lambda *a:1)
    monkeypatch.setattr(service.kline_repo,'get_bars',lambda *a,**k:values)
    monkeypatch.setattr(service,'_get_cache',lambda *a:None)
    monkeypatch.setattr(service,'_set_cache',lambda *a:None)
    monkeypatch.setattr(service,'_cache_key',lambda *a,**k:'isolated-main-overlays')
    return values

@pytest.mark.parametrize('period',['1d','1w','1mon','15m'])
@pytest.mark.parametrize('pandas_enabled',[False,True])
def test_native_overlays_warmup_and_latest(monkeypatch,bars,period,pandas_enabled):
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':pandas_enabled,'revision':1})
    monkeypatch.setattr(service,'_bars_to_df',lambda *a:pytest.fail('Main overlays must use SDK'))
    full=service.compute_indicators(None,'1',period,KEYS,CUSTOM,limit=80)
    page=service.compute_indicators(None,'1',period,KEYS,CUSTOM,start=bars[40].ts,end=bars[-1].ts)
    recent=service.compute_indicators(None,'1',period,KEYS,CUSTOM,limit=5)
    assert page==full[40:]
    assert recent==full[-5:]
    assert len(full)==80
    for key in KEYS:
        assert registry.REGISTRY[key]['placement']=='main'
        assert registry.REGISTRY[key]['engines']==['sdk']
        for field in registry.REGISTRY[key]['native_outputs']: assert full[-1][field] is not None

@pytest.mark.parametrize('name,params',[('boll',{'p':0}),('boll',{'p':True}),('boll',{'p':float('inf')}),('boll',{'n':2.5}),('dma',{'a':0}),('dma',{'a':1.01}),('dma',{'a':'0.2'}),('dma',{'a':True}),('sma',{'n':5,'m':6}),('ema',{'n':10**400})])
def test_invalid_main_parameters(client,name,params):
    result=client.get('/api/v1/indicators',params={'symbol':'300502','names':name,'params':json.dumps({name:params})})
    assert result.status_code==400
