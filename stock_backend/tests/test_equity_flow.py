from app.services import equity_flow as flow


def quote(code='000001'):
    return dict(code=code,name=code,market='SZSE',industry='银行',close=10,change_pct=1,data_date=20261106)


def test_zero_is_not_missing_and_ratio_uses_flow_day_amount():
    history={'000001':{20261105:dict(main_net=0,jumbo_net=5,big_net=-5,mid_net=0,small_net=0)}}
    row=flow.aggregate([quote()],history,{('000001',20261105):1000,('000001',20261106):2000})[0]
    assert row['flow_date']=='20261105'
    assert row['main_ratio']==0 and row['main_net']==0
    history['000001'][20261105]['main_net']=100
    assert flow.aggregate([quote()],history,{('000001',20261105):1000})[0]['main_ratio']==10
    assert flow.aggregate([quote()],history,{('000001',20261106):2000})[0]['main_ratio'] is None


def test_complete_windows_and_missing_sessions():
    dates=list(range(20261001,20261021))
    history={'000001':{d:{'main_net':2} for d in dates},'000002':{d:{'main_net':0} for d in dates}}
    row=flow.aggregate([quote()],history,{})[0]
    assert [row['main_5'],row['main_10'],row['main_20']]==[10,20,40]
    del history['000001'][dates[-3]]
    row=flow.aggregate([quote()],history,{})[0]
    assert row['main_5'] is None and row['main_20'] is None


def test_missing_stock_and_invalid_values_stay_null():
    row=flow.aggregate([quote()],{},{} )[0]
    assert row['flow_date'] is None and row['main_net'] is None
    row=flow.aggregate([quote()],{'000001':{20261106:{'main_net':float('nan')}}},{('000001',20261106):100})[0]
    assert row['main_net'] is None and row['main_ratio'] is None


def test_endpoint_contract(monkeypatch):
    from app.api.v1.stockdb import equity_flows
    monkeypatch.setattr(flow,'snapshot',lambda:dict(items=[],loading=True))
    assert equity_flows()==dict(code=0,msg='ok',data=dict(items=[],loading=True))


def test_market_wide_missing_flow_day_is_not_silently_skipped():
    dates=list(range(20261001,20261021))
    records={d:{'main_net':2} for d in dates if d!=20261018}
    row=flow.aggregate([quote()],{'000001':records},{},dates)[0]
    assert row['main_5'] is None and row['main_20'] is None


def test_build_loads_calendar_for_old_fallback_and_keeps_missing_day_null(monkeypatch):
    from datetime import date,timedelta
    from unittest.mock import Mock
    first=date(2026,7,29)
    days=[int((first+timedelta(days=n)).strftime('%Y%m%d')) for n in range(28)
          if (first+timedelta(days=n)).weekday()<5]
    assert len(days)==20
    old=[dict(code='920002',date=d,main_net=0) for d in days]
    recent=dict(code='000001',date=20261106,main_net=10)
    calendar_queries=[]
    def query(command,table,**params):
        if table=='资金流':
            if params['k1']=='key:920002': return old
            return [recent] if params['k1']=='qz:0' else []
        if params['k1']=='all:':return [['920002',1000]]
        left,right=map(int,params['k2'][4:].split(','))
        calendar_queries.append((left,right))
        return [[d,'000001'] for d in days+[20261106] if left<=d<=right] if params['k1']=='qz:0' else []
    provider=Mock();provider.query.side_effect=query
    monkeypatch.setattr(flow,'StockDBProvider',lambda:provider)
    monkeypatch.setattr(flow.equity_table,'snapshot',lambda:dict(date=20261106,industries=[],items=[quote(),quote('920002')]))
    result={r['code']:r for r in flow.build()['items']}
    assert result['920002']['flow_date']=='20260825'
    assert [result['920002'][f'main_{n}'] for n in (5,10,20)]==[0,0,0]
    assert (20260729,20260825) in calendar_queries
    # A missing record within the historical range must not become a zero or
    # be skipped as though it were a non-trading day.
    old.pop(-3)
    result={r['code']:r for r in flow.build()['items']}
    assert result['920002']['main_5'] is None
    assert result['920002']['main_20'] is None


def test_calendar_ranges_merge_overlapping_windows_without_bridging_years():
    result=flow.calendar_ranges(20260902,{
        'a':{20260729:{},20260825:{}},'b':{20260801:{},20260826:{}},
        'c':{20210101:{},20210129:{}},'d':{20260901:{},20260903:{}}})
    assert result==[(20210101,20210129),(20260729,20260826),(20260901,99991231)]
