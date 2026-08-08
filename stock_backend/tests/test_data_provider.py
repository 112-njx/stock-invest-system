"""1.4 DataProvider 单测：mock 外部 akshare 源，验证取数/清洗/回填。"""

from datetime import UTC, datetime

import pandas as pd
from app.data_providers.base import RealtimeSymbol
from app.data_providers.eastmoney import EastMoneyProvider


class MockAk:
    """mock akshare：各函数返回固定 DataFrame。"""

    @staticmethod
    def stock_zh_a_hist(**kwargs):
        return pd.DataFrame(
            {
                "日期": ["2026-07-30", "2026-07-31", "2026-08-01"],
                "开盘": [100.0, 101.0, 0.0],  # 第三行异常价（0）
                "最高": [102.0, 103.0, 99.0],
                "最低": [99.0, 100.0, 98.0],
                "收盘": [101.0, 102.0, 98.5],
                "成交量": [1000, 2000, 0],
                "成交额": [100000.0, 200000.0, 0.0],
            }
        )

    @staticmethod
    def stock_zh_a_hist_min_em(**kwargs):
        return pd.DataFrame(
            {
                "时间": ["2026-08-07 10:00:00", "2026-08-07 10:15:00"],
                "开盘": [101.0, 102.0],
                "最高": [103.0, 104.0],
                "最低": [100.0, 101.0],
                "收盘": [102.0, 103.0],
                "成交量": [500, 600],
                "成交额": [50000.0, 60000.0],
            }
        )

    @staticmethod
    def stock_board_industry_name_em():
        return pd.DataFrame(
            {
                "板块代码": ["BK0447", "BK1036"],
                "板块名称": ["半导体", "通信设备"],
                "最新价": [2000.0, 1500.0],
                "涨跌额": [20.0, -10.0],
                "涨跌幅": [1.01, -0.66],
                "换手率": [1.5, 0.8],
            }
        )

    @staticmethod
    def stock_zh_a_spot_em():
        return pd.DataFrame(
            {
                "代码": ["600519", "000001"],
                "名称": ["贵州茅台", "平安银行"],
                "最新价": [1350.6, 12.3],
                "涨跌额": [10.2, 0.1],
                "涨跌幅": [0.71, 0.82],
                "今开": [1345.0, 12.1],
                "最高": [1355.0, 12.4],
                "最低": [1338.0, 12.0],
                "昨收": [1340.4, 12.2],
                "成交量": [50000, 90000],
                "成交额": [7.2e9, 1.1e9],
                "换手率": [0.8, 0.5],
                "振幅": [1.5, 3.2],
            }
        )

    @staticmethod
    def stock_zh_index_spot_em(symbol=None):
        return pd.DataFrame(
            {
                "代码": ["000001", "000300"],
                "名称": ["上证指数", "沪深300"],
                "最新价": [3896.49, 4200.0],
                "涨跌额": [39.69, 20.0],
                "涨跌幅": [1.02, 0.48],
                "今开": [3880.0, 4180.0],
                "最高": [3940.0, 4210.0],
                "最低": [3870.0, 4170.0],
                "昨收": [3856.8, 4180.0],
            }
        )

    @staticmethod
    def index_global_spot_em():
        return pd.DataFrame(
            {
                "代码": ["DJIA", "N225"],
                "名称": ["道琼斯", "日经225"],
                "最新价": [40000.0, 39000.0],
                "涨跌额": [100.0, -50.0],
                "涨跌幅": [0.25, -0.13],
            }
        )


def _provider() -> EastMoneyProvider:
    p = EastMoneyProvider()
    p._ak = MockAk()
    p.retry_times = 1
    return p


def test_fetch_kline_stock_cleans_bad_rows():
    p = _provider()
    bars = p.fetch_kline(
        "600519", "1d", datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC), asset_type="stock"
    )
    assert len(bars) == 2  # 第三行 0 价被清洗剔除
    assert bars[0].close == 101.0
    assert bars[0].ts.year == 2026


def test_fetch_kline_15m_converts_tz_to_utc():
    p = _provider()
    bars = p.fetch_kline(
        "600519",
        "15m",
        datetime(2026, 8, 7, 0, 0, tzinfo=UTC),
        datetime(2026, 8, 8, 0, 0, tzinfo=UTC),
        asset_type="stock",
    )
    assert len(bars) == 2
    assert bars[0].ts.tzinfo is not None  # 已转 UTC


def test_fetch_realtime_stock_batch():
    p = _provider()
    symbols = [
        RealtimeSymbol(code="600519", name="贵州茅台", asset_type="stock"),
        RealtimeSymbol(code="999999", name="不存在", asset_type="stock"),
    ]
    quotes = p.fetch_realtime(symbols)
    assert quotes[0].price == 1350.6
    assert quotes[0].turnover == 0.8
    assert quotes[1].available is False  # 未命中降级


def test_fetch_realtime_index_matches_by_code_and_name():
    p = _provider()
    symbols = [
        RealtimeSymbol(code="000001", name="上证指数", asset_type="index"),
        RealtimeSymbol(code="DJI", name="道琼斯指数", asset_type="index"),
    ]  # 名称为子串匹配
    quotes = p.fetch_realtime(symbols)
    assert quotes[0].price == 3896.49
    assert quotes[1].available is True and quotes[1].change_pct == 0.25


def test_fetch_realtime_industry_index():
    p = _provider()
    quotes = p.fetch_realtime([RealtimeSymbol(name="半导体", asset_type="industry_index")])
    assert quotes[0].price == 2000.0
    assert quotes[0].change_pct == 1.01


def test_resolve_index_code_by_name():
    p = _provider()
    assert p.resolve_index_code("半导体") == "BK0447"
    assert p.resolve_index_code("不存在") is None
