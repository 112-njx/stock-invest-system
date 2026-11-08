"""Final indicator batches: public API, engine choice, index isolation and options."""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from app.services import indicator_service as service, indicator_policy, sdk_indicators
from tests.test_trend_volume_channels import bars

STATS=['std','sum','hhv','llv','ref']
INDEX={'members':[{'code':'600519','weight':3},{'code':'300502','weight':1}],
       'weighting':'custom','base':1000,'start':'2025-01-01'}


@pytest.mark.parametrize('period',['1d','1w','1mon','15m'])
@pytest.mark.parametrize('pandas_enabled',[False,True])
def test_statistics_native_controls_paging_and_crosses(monkeypatch,bars,period,pandas_enabled):
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':pandas_enabled,'revision':1})
    monkeypatch.setattr(service,'_bars_to_df',lambda *a:pytest.fail('Field/cross controls must use native SDK'))
    params={k:{'n':7,'field':'volume'} for k in STATS}
    params['macd']={'cross':True,'fast':7,'slow':21,'signal':5}
    names=STATS+['macd']
    full=service.compute_indicators(None,'1',period,names,params,limit=180)
    tail=service.compute_indicators(None,'1',period,names,params,start=bars[100].ts,end=bars[-1].ts)
    assert tail==full[100:]
    assert full[-1]['hhv']<1200
    assert all(r['macd_cross'] in (-1,0,1) for r in full)
    assert any(r['macd_cross']!=0 for r in full)


@pytest.mark.parametrize('key,params',[
    ('std',{'field':'bad'}),('std',{'field':True}),('ema',{'field':'volume'}),('ma',{'field':'open'}),
    ('std',{'n':0}),('sum',{'n':10001}),('ref',{'n':True}),('macd',{'cross':1}),('rsi',{'cross':True}),
    ('zhishu',{}),('zhishu',{'members':[{'code':'600519','weight':-1}]}),
    ('zhishu',{'members':[{'code':'600519','weight':0}],'weighting':'custom'}),
    ('zhishu',{'members':[{'code':'600519'},{'code':'600519'}]}),
    ('zhishu',{'members':[{'code':'600519'}],'start':'2020-02-31'})])
def test_api_validates_controls_and_index_before_data_access(client,key,params):
    response=client.get('/api/v1/indicators',params={'symbol':'300502','names':key,'params':json.dumps({key:params})})
    assert response.status_code==400


def test_index_uses_current_bar_labels_avoids_stale_cache_and_isolates_sdk_call(monkeypatch,bars):
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':True,'revision':1})
    monkeypatch.setattr(service,'_get_cache',lambda *a:pytest.fail('Constituent changes cannot reuse current-stock cache'))
    calls=[]
    def calculate(rows,names,params,*,period=None):
        calls.append((names,period,params))
        return [{**r,'zhishu_close':1000+i,'zhishu_count':2} for i,r in enumerate(rows)]
    monkeypatch.setattr(sdk_indicators,'calculate',calculate)
    for period in ['1d','1w','1mon','15m']:
        result=service.compute_indicators(None,'1',period,['zhishu'],{'zhishu':INDEX},limit=5)
        assert len(result)==5 and result[-1]['zhishu_close']==1179
        assert result[-1]['close']==bars[-1].close
        assert calls[-1]==(['zhishu'],period,{'zhishu':INDEX})
    bars.clear()
    assert service.compute_indicators(None,'1','1d',['zhishu'],{'zhishu':INDEX})==[]


def test_index_and_statistics_coexist_without_overwriting_each_other(monkeypatch,bars):
    monkeypatch.setattr(indicator_policy,'read',lambda:{'pandas_enabled':False,'revision':1})
    original=sdk_indicators.calculate
    def calculate(rows,names,params,*,period=None):
        if names==['zhishu']:
            return [{**r,'zhishu_close':2000.,'zhishu_count':2} for r in rows]
        return original(rows,names,params)
    monkeypatch.setattr(sdk_indicators,'calculate',calculate)
    result=service.compute_indicators(None,'1','1d',['std','zhishu'],{'zhishu':INDEX},limit=5)
    assert result[-1]['std'] is not None
    assert result[-1]['zhishu_close']==2000
    assert result[-1]['close']==bars[-1].close
