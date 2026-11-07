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
