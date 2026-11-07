from unittest.mock import Mock
from threading import Event
from app.services import equity_table as table


def test_returns_adjusts_dividend_and_rejects_missing_baseline():
    assert round(table.returns([], [(20260101, 1.1)], (20251231,100), (20261106,100)), 6) == 10
    assert table.returns([], [], None, (20261106,100)) is None
    assert table.returns([], [], (20261106,100), (20251106,100)) is None


def test_build_keeps_units_static_pe_missing_and_ignores_empty_records(monkeypatch):
    row=dict(code='000001',name='银行',date=20261106,close=11,pre_close=10,open=10,high=12,low=9,
             volume=200,amount=2000,float_share=10000,total_share=20000,vol_ratio=.8,pe_ttm=5)
    def query(cmd, table_name, **params):
        if cmd=='keys': return ['日k:600519:20251231','日k:600519:20261106']
        if table_name=='复权*': return []
        if table_name=='板块*': return [('b',dict(code='b',name='银行',category='申万一级',symbols=['000001']))]
        if params.get('k2')=='key:20251231': return [None,dict(code='000001',date=20251231,close=10)]
        if params.get('k2')=='key:20261106': return [None,row]
        if params.get('ap'): return [[20261106,'000001',11]] if params['k1']=='qz:0' else []
        raise AssertionError(params)
    provider=Mock();provider.query.side_effect=query
    monkeypatch.setattr(table,'StockDBProvider',lambda:provider)
    monkeypatch.setattr(table,'get_directory',lambda:dict(items=[dict(code='000001',name='银行',market='SZSE')]))
    data=table.build()['items'][0]
    assert data['volume']==200 and data['float_share']==10000
    assert data['turnover']==2 and data['amplitude']==30
    assert data['pe'] is None and data['pe_ttm']==5 and data['vol_ratio']==.8
    assert round(data['return_ytd'])==10 and data['return_20'] is None


def test_snapshot_returns_existing_data_while_refresh_blocks(monkeypatch):
    entered,release=Event(),Event()
    def build():
        entered.set();release.wait(3);return dict(items=[],date=20261106)
    old=dict(items=[],date=20261105)
    monkeypatch.setattr(table,'_state',old);monkeypatch.setattr(table,'_checked',0)
    monkeypatch.setattr(table,'_running',False);monkeypatch.setattr(table,'build',build)
    monkeypatch.setattr(table,'get_redis_client',Mock())
    try:
        assert table.snapshot()['date']==20261105
        assert entered.wait(1)
        assert table.snapshot()['date']==20261105
    finally:
        release.set()
        import time
        deadline=time.monotonic()+2
        while table._running and time.monotonic()<deadline: time.sleep(.01)
