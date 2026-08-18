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
        # "油气开采" 模拟种子名"油气开采及服务"与东财板块名不完全一致的场景
        return pd.DataFrame(
            {
                "板块代码": ["BK0447", "BK1036", "BK0426"],
                "板块名称": ["半导体", "通信设备", "油气开采"],
                "最新价": [2000.0, 1500.0, 3000.0],
                "涨跌额": [20.0, -10.0, 5.0],
                "涨跌幅": [1.01, -0.66, 0.17],
                "换手率": [1.5, 0.8, 0.9],
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
                "总市值": [1.7e12, 2.4e11],
                "市盈率-动态": [25.3, 5.2],
            }
        )

    @staticmethod
    def fund_etf_spot_em():
        return pd.DataFrame(
            {
                "代码": ["510300", "159915"],
                "名称": ["沪深300ETF", "创业板ETF"],
                "最新价": [4.2, 2.6],
                "IOPV实时估值": [4.19, 2.61],
                "基金折价率": [-0.24, 0.38],  # 负=溢价，正=折价
                "涨跌额": [0.01, 0.02],
                "涨跌幅": [0.24, 0.78],
                "成交量": [5000000, 3000000],
                "成交额": [2.1e7, 7.8e6],
            }
        )

    @staticmethod
    def stock_index_pe_lg(symbol="沪深300"):
        return pd.DataFrame(
            {
                "日期": ["2026-08-17", "2026-08-14"],
                "指数": [symbol, symbol],
                "等权静态市盈率": [11.2, 11.0],
                "静态市盈率": [10.8, 10.6],
                "等权滚动市盈率": [13.1, 12.9],
                "滚动市盈率": [12.5, 12.3],
                "滚动市盈率中位数": [12.8, 12.7],
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
    assert p.resolve_index_code("油气开采及服务") == "BK0426"  # 评分模糊匹配回填 code
    assert p.resolve_index_code("不存在") is None


def test_fetch_realtime_stock_extracts_fundamentals():
    p = _provider()
    quotes = p.fetch_realtime([RealtimeSymbol(code="600519", name="贵州茅台", asset_type="stock")])
    assert quotes[0].extra["market_cap"] == 1.7e12
    assert quotes[0].extra["pe"] == 25.3


def test_fetch_realtime_etf_extracts_premium():
    p = _provider()
    quotes = p.fetch_realtime([RealtimeSymbol(code="510300", name="沪深300ETF", asset_type="etf")])
    assert quotes[0].extra["nav"] == 4.19
    assert quotes[0].extra["premium"] == 0.24  # 基金折价率 -0.24 → 溢价率 +0.24


def test_fetch_realtime_overseas_index_volume_none():
    p = _provider()
    # 海外指数 index_global_spot_em 无"成交量/额"列，volume/amount 应为 None（而非 0）
    quotes = p.fetch_realtime([RealtimeSymbol(code="DJI", name="道琼斯指数", asset_type="index")])
    assert quotes[0].available is True
    assert quotes[0].volume is None
    assert quotes[0].amount is None


def test_fetch_realtime_industry_fuzzy_match():
    p = _provider()
    # 种子名"油气开采及服务"与东财板块名"油气开采"不一致，用名称前3字子串兜底匹配
    quotes = p.fetch_realtime([RealtimeSymbol(code="", name="油气开采及服务", asset_type="industry_index")])
    assert quotes[0].available is True
    assert quotes[0].price == 3000.0


def test_fetch_realtime_industry_code_match():
    p = _provider()
    # 板块 code 已回填（BKxxxx）时优先按板块代码精确匹配，名称不一致也能命中
    quotes = p.fetch_realtime([RealtimeSymbol(code="BK1036", name="通信设备(名称不一致)", asset_type="industry_index")])
    assert quotes[0].available is True
    assert quotes[0].price == 1500.0


def test_fetch_index_pe_covered_and_uncovered():
    p = _provider()
    result = p.fetch_index_pe(["沪深300", "上证50", "道琼斯指数", "现货黄金"])
    assert result["沪深300"] == 12.5  # 取最新日期"滚动市盈率"
    assert result["上证50"] == 12.5
    assert result["道琼斯指数"] is None  # 不在乐咕覆盖范围
    assert result["现货黄金"] is None


def test_industry_score_rules():
    """通用评分模糊匹配：正确匹配分类后缀/前后缀差异，拒绝否定词与过长扩展。"""
    from app.data_providers.eastmoney import _industry_score

    # 正确匹配（≥阈值 75）
    assert _industry_score("通信设备", "通信设备") == 100
    assert _industry_score("游戏", "游戏Ⅲ") >= 75      # 剥离罗马后缀
    assert _industry_score("证券", "证券Ⅱ") >= 75
    assert _industry_score("煤炭开采加工", "煤炭开采") >= 75   # seed 是板块名前缀扩展
    assert _industry_score("油气开采及服务", "油气开采") >= 75
    # 拒绝误匹配（< 阈值）
    assert _industry_score("白酒", "非白酒") < 75          # 否定前缀
    assert _industry_score("消费", "消费电子零部件及组装") < 75  # 扩展过长
    assert _industry_score("消费", "消费电子") < 75         # 2字短词前缀误配（消费≠消费电子）
    assert _industry_score("军工", "军工电子") < 75         # 2字短词前缀误配
    assert _industry_score("创新药", "化学制药") < 75       # 无语义/字面关联


def test_map_industry_rejects_bad_name_match():
    """板块名与种子行业语义不符（否定/过长扩展）时不得匹配，诚实返回不可用。"""
    from app.data_providers.eastmoney import _map_industry_spot

    df = pd.DataFrame(
        {
            "板块代码": ["BK1001", "BK1002"],
            "板块名称": ["非白酒", "消费电子零部件及组装"],
            "最新价": [1000.0, 2000.0],
            "涨跌额": [1.0, 2.0],
            "涨跌幅": [0.1, 0.2],
            "换手率": [0.5, 0.6],
        }
    )
    q1 = _map_industry_spot(df, RealtimeSymbol(name="白酒", asset_type="industry_index"))
    assert q1.available is False
    q2 = _map_industry_spot(df, RealtimeSymbol(name="消费", asset_type="industry_index"))
    assert q2.available is False
