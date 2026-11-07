"""Shared catalog, validation and engine-routing contracts."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from app.services import indicator_registry as registry, indicator_service as service, indicator_policy, sdk_indicators

def test_catalog_lists_only_delivered_indicators(client):
    response = client.get('/api/v1/indicators/catalog')
    assert response.status_code == 200
    assert response.json()['data']['indicators'] == registry.DEFINITIONS
    assert set(registry.REGISTRY) == {'ma','macd','kdj','volume','amount','rsi','wr','cci','atr','boll','ema','expma','bbi','wma','sma','dma','bias','psy','dpo','mtm','roc','dmi','trix','dfma','mass','vr','cr','emv','brar','obv','mfi','asi','taq','ktn','xsii','std','sum','hhv','llv','ref','zhishu'}
    for definition in registry.DEFINITIONS:
        assert all(key in definition for key in ('parameters','series','inputs','placement','reference_lines','engines'))

@pytest.mark.parametrize('name,params', [('ma',{'periods':[True]}), ('macd',{'fast':1.5}),('kdj',{'n':0}),('amount',{'n':3}),('macd',{'bad':2})])
def test_registry_rejects_invalid_parameters(name,params):
    with pytest.raises(ValueError): registry.validate_parameters(name,params)

def test_sdk_only_catalog_entry_ignores_global_pandas_switch(monkeypatch):
    # Future SDK-only entries must work without a new pandas class or service branch.
    definition = {**registry.REGISTRY['macd'],'key':'probe','engines':['sdk']}
    monkeypatch.setitem(registry.REGISTRY,'probe',definition)
    monkeypatch.setattr(service,'INDICATOR_NAMES',set(registry.REGISTRY))
    monkeypatch.setattr(service.market_service,'resolve_symbol_id',lambda *a:1)
    bars = [SimpleNamespace(ts=datetime(2026,1,1,tzinfo=UTC)+timedelta(days=i),source='stockdb',open=10,high=12,low=9,close=11,volume=100,amount=1000) for i in range(40)]
    monkeypatch.setattr(service.kline_repo,'get_bars',lambda *a,**k:bars)
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':True,'revision':1})
    monkeypatch.setattr(service,'_cache_key',lambda *a,**k:'isolated-registry')
    monkeypatch.setattr(service,'_get_cache',lambda *a:None)
    monkeypatch.setattr(service,'_set_cache',lambda *a:None)
    names = []
    def calculate(rows, chosen, params):
        names.extend(chosen)
        return [{**r,'probe':123} for r in rows]
    monkeypatch.setattr(sdk_indicators,'calculate',calculate)
    result=service.compute_indicators(None,'1','1d',['probe','volume'],limit=5)
    assert names == ['probe']
    assert result[-1]['probe'] == 123
    assert result[-1]['volume_ma10'] == 100
