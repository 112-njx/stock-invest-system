"""Regression checks for close selection, cap areas and legacy memberships."""
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from app.services import heatmap_service as hm


def row(code, cap, date=20261105):
    return [date, code, code, 11, 10, cap, cap]


def test_cap_area_does_not_cancel_and_memberships_are_unique():
    boards = [dict(code='large', name='综合', symbols=['a', 'b', 'c']),
              dict(code='small', name='行业', symbols=['a', 'b'])]
    days = {20261104: {s: row(s, 100, 20261104) for s in 'abc'},
            20261105: {'a': row('a', 120), 'b': row('b', 80), 'c': row('c', 100)}}
    result = hm.aggregate(boards, days, 20261105, 20261104)
    assert result['count'] == 3
    assert result['duplicates'] == 2
    assert result['zero'] == 1
    sector = result['boards'][1]
    assert sector['value'] == 40
    assert sector['change'] == 0
    assert {s['code'] for s in sector['children']} == {'a', 'b'}


def test_load_ignores_partial_new_session_and_intraday(monkeypatch):
    codes = [str(n) for n in range(300)]
    boards = [('board', dict(code='sw', name='行业', category='申万一级', symbols=codes))]
    rows = [row(s, 100, d) for d in (20261103, 20261104, 20261105) for s in codes
            if d != 20261105 or int(s) < 100]
    def fake(client, cmd, table, **params):
        if table == '板块*': return boards
        if cmd == 'keys': return ['日k:600519:'+str(d) for d in (20261103, 20261104, 20261105)]
        return rows if params['k1'] == 'qz:0' else []
    monkeypatch.setattr(hm.rd, '_client', lambda: nullcontext(None))
    monkeypatch.setattr(hm.rd, '_rd', fake)
    for hour in (10, 16):
        result = hm.load(datetime(2026, 11, 5, hour, tzinfo=ZoneInfo('Asia/Shanghai')))
        assert result['date'] == 20261104


def test_outage_preserves_published_snapshot(monkeypatch):
    monkeypatch.setattr(hm, '_cached', {'date': 20261104, 'boards': []})
    monkeypatch.setattr(hm, '_checked', 0)
    monkeypatch.setattr(hm, 'get_redis_client', Mock())
    monkeypatch.setattr(hm, 'load', Mock(side_effect=hm.rd.StockDBError('offline')))
    assert hm.snapshot()['date'] == 20261104
    assert hm.snapshot()['warning']


def test_today_requires_stable_observations(monkeypatch):
    today = int(datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d'))
    monkeypatch.setattr(hm, '_cached', {'date': today-1, 'boards': []})
    monkeypatch.setattr(hm, '_checked', 0)
    monkeypatch.setattr(hm, '_candidate', ('', 0))
    monkeypatch.setattr(hm, 'get_redis_client', Mock())
    monkeypatch.setattr(hm, 'load', lambda now: {'date': today, 'boards': []})
    assert hm.snapshot()['date'] == today-1
    assert '校验' in hm.snapshot()['warning']
    monkeypatch.setattr(hm, '_checked', 0)
    monkeypatch.setattr(hm, '_candidate', (hm._candidate[0], hm.time()-61))
    assert hm.snapshot()['date'] == today


@pytest.mark.parametrize('cap', [None, 0, -1, float('nan'), float('inf')])
def test_invalid_market_caps_are_excluded(cap):
    assert not hm.valid(row('a', cap))
