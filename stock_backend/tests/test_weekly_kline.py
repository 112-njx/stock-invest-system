"""周 K 使用本地日 K 聚合及翻页。"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.weekly_kline import get_weekly_bars


def test_weekly_ohlc_and_history_cursor(monkeypatch):
    dates = [
        (1, 10, 12, 9, 11, 100),
        (2, 11, 14, 10, 13, 200),
        (12, 20, 22, 19, 21, 400),
        (13, 21, 24, 20, 23, 500),
    ]
    daily = [SimpleNamespace(ts=datetime(2026, 10, day, tzinfo=UTC), open=o, high=h, low=low,
                             close=c, volume=vol, amount=vol * 10) for day, o, h, low, c, vol in dates]
    monkeypatch.setattr("app.services.weekly_kline.kline_repo.get_bars", lambda *args, **kwargs: daily)

    latest = get_weekly_bars(None, 1, None, None, 1)
    assert len(latest) == 1
    assert (latest[0].open, latest[0].high, latest[0].low, latest[0].close) == (20, 24, 19, 23)
    assert (latest[0].volume, latest[0].amount) == (900, 9000)

    older = get_weekly_bars(None, 1, datetime(2026, 9, 1, tzinfo=UTC),
                            datetime(2026, 10, 4, 23, 59, tzinfo=UTC), 60)
    assert len(older) == 1
    assert (older[0].ts.day, older[0].open, older[0].high, older[0].low, older[0].close) == (2, 10, 14, 9, 13)
