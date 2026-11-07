from datetime import date,timedelta
from unittest.mock import Mock
import pytest
from app.services import stock_flow_history as history


def source(monkeypatch, missing=None):
    first=date(2026,10,12)
    sessions=[int((first+timedelta(days=i)).strftime('%Y%m%d')) for i in range(26) if (first+timedelta(days=i)).weekday()<5]
    records={d:dict(code='000001',date=d,main_net=0,jumbo_net=1,big_net=-1,mid_net=0,small_net=0) for d in sessions if d!=missing}
    def query(cmd,table,**params):
        if table=='资金流' and cmd=='keys':return ['资金流:000001:'+('20190801' if params['num']==1 else '20261106')]
        left,right=map(int,params['k2'][4:].split(','))
        if table=='资金流': return [r for d,r in records.items() if left<=d<=right]
        return ['日k:'+params['k1'][4:]+':'+str(d) for d in sessions if left<=d<=right]
    provider=Mock();provider.query.side_effect=query
    monkeypatch.setattr(history,'StockDBProvider',lambda:provider)
    return sessions


def test_range_is_independent_of_latest_and_missing_is_not_zero(monkeypatch):
    source(monkeypatch,20261104)
    result=history.load('000001',date(2026,11,3),date(2026,11,5))
    assert result['coverage']==dict(start='20190801',end='20261106')
    assert result['latest']['date']==20261106
    assert [r['date'] for r in result['rows']]==[20261103,20261104,20261105]
    assert result['rows'][0]['main_net']==0
    assert result['rows'][1]['main_net'] is None
    assert result['totals']['5'] is None


def test_complete_windows_are_zero_and_default_is_bounded(monkeypatch):
    source(monkeypatch)
    result=history.load('000001')
    assert result['totals']=={'5':0,'10':0,'20':0}
    assert (date.fromisoformat(result['end'])-date.fromisoformat(result['start'])).days==65


def test_invalid_date_range_is_rejected(monkeypatch):
    source(monkeypatch)
    with pytest.raises(ValueError):history.load('000001',date(2010,1,1),date(2026,11,6))


def test_no_local_history_has_no_invented_coverage(monkeypatch):
    provider=Mock();provider.query.return_value=[]
    monkeypatch.setattr(history,'StockDBProvider',lambda:provider)
    result=history.load('920999')
    assert result['coverage'] is None and result['latest'] is None and result['rows']==[]
