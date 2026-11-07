from unittest.mock import Mock
from threading import Event
from app.services import equity_table as table


def test_returns_adjusts_dividend_and_rejects_missing_baseline():
    assert round(table.returns([], [(20260101, 1.1)], (20251231,100), (20261106,100)), 6) == 10
    assert table.returns([], [], None, (20261106,100)) is None
    assert table.returns([], [], (20261106,100), (20251106,100)) is None


def install_source(monkeypatch, records, directory_date='20261105'):
    provider = Mock()
    codes = sorted({r['code'] for r in records if isinstance(r,dict)})
    def query(cmd, table_name, **params):
        if table_name == '复权*': return []
        if table_name == '板块*': return []
        # No single-stock date calendar may be consulted.
        assert cmd == 'vals'
        k1,k2=params['k1'],params['k2']
        if params.get('ap'):
            start,end=map(int,k2.removeprefix('fwd:').split(','))
            return [[r['date'],r['code'],r['close']] for r in records if isinstance(r,dict)
                    and r['code'].startswith(k1.removeprefix('qz:')) and start <= r['date'] <= end]
        if k1 == 'all:':
            return [None]+[r for r in records if isinstance(r,dict) and r['date']==int(k2.removeprefix('key:'))]
        code=k1.removeprefix('key:')
        selected=[r for r in records if isinstance(r,dict) and r['code']==code]
        if k2.startswith('fwd:'):
            start,end=map(int,k2[4:].split(','))
            selected=[r for r in selected if start<=r['date']<=end]
        selected.sort(key=lambda r:r['date'])
        n=params.get('num')
        return selected[n:] if n and n<0 else selected[:n]
    provider.query.side_effect=query
    monkeypatch.setattr(table,'StockDBProvider',lambda:provider)
    monkeypatch.setattr(table,'get_directory',lambda:dict(items=[dict(code=c,name=c,market='SZSE',latest_date=directory_date) for c in codes]))
    return provider


def bar(code,date,close):
    return dict(code=code,name=code,date=date,close=close,pre_close=10,open=10,high=12,low=9,
                volume=200,amount=2000,float_share=10000,total_share=20000,vol_ratio=.8,pe_ttm=5)


def test_build_keeps_units_static_pe_missing_and_ignores_empty_records(monkeypatch):
    install_source(monkeypatch,[None,bar('000001',20251231,10),bar('000001',20261106,11)])
    data=table.build()['items'][0]
    assert data['volume']==200 and data['float_share']==10000
    assert data['turnover']==2 and data['amplitude']==30
    assert data['pe'] is None and data['pe_ttm']==5 and data['vol_ratio']==.8
    assert round(data['return_ytd'])==10 and data['return_20'] is None


def test_market_scan_finds_newer_data_than_directory_or_reference_stock(monkeypatch):
    install_source(monkeypatch,[bar('600519',20261105,10),bar('000001',20261105,10),
                                bar('000001',20261106,11)])
    result=table.build()
    assert result['date']==20261106
    by_code={r['code']:r for r in result['items']}
    assert by_code['000001']['close']==11
    assert by_code['600519']['data_date']==20261105


def test_invalid_latest_close_falls_back_without_aborting_other_stocks(monkeypatch):
    # Every invalid numeric representation must be isolated from the market batch.
    for invalid in (None,float('nan'),float('inf'),0,-1,True):
        install_source(monkeypatch,[bar('000001',20251231,10),bar('000001',20261105,10),
                                    bar('000001',20261106,invalid),bar('000002',20261106,12)])
        by_code={r['code']:r for r in table.build()['items']}
        assert by_code['000001']['data_date']==20261105
        assert by_code['000001']['close']==10
        assert by_code['000001']['return_ytd']==0
        assert by_code['000002']['close']==12
        assert table.returns([],[],(20251231,10),(20261106,invalid)) is None


def test_stock_without_valid_close_is_skipped_and_other_stock_survives(monkeypatch):
    install_source(monkeypatch,[bar('000001',20261106,None),bar('000002',20261106,12)])
    assert [r['code'] for r in table.build()['items']]==['000002']


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


def test_endpoint_uses_shared_frontend_response_contract(monkeypatch):
    from app.api.v1.stockdb import equities
    monkeypatch.setattr(table, 'snapshot', lambda: dict(items=[], loading=True))
    response = equities()
    assert response['code'] == 0
    assert response['data']['loading'] is True
