"""V0.2 阶段四测试：独立 Provider（Sina/THS）+ DataProviderFactory 优先级链/熔断/健康检查。"""

import inspect
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
from app.data_providers.base import BaseDataProvider, KlineBar, RealtimeQuote, RealtimeSymbol, unavailable_quote
from app.data_providers.eastmoney import EastMoneyProvider
from app.data_providers.factory import DataProviderFactory, ProviderCircuit, reset_provider
from app.data_providers.sina import SinaProvider, to_sina_index
from app.data_providers.ths import THSProvider


def _df_daily():
    return pd.DataFrame(
        {
            "date": ["2026-08-18", "2026-08-19"],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 2000],
        }
    )


def _df_ths():
    return pd.DataFrame(
        {
            "日期": ["2026-08-18", "2026-08-19"],
            "开盘价": [100.0, 101.0],
            "最高价": [102.0, 103.0],
            "最低价": [99.0, 100.0],
            "收盘价": [101.0, 102.0],
            "成交量": [1000, 2000],
            "成交额": [1e6, 2e6],
        }
    )


def _df_sina_spot():
    return pd.DataFrame(
        {
            "代码": ["sh600519", "sz000001"],
            "名称": ["贵州茅台", "平安银行"],
            "最新价": [1350.6, 12.3],
            "涨跌额": [10.2, 0.1],
            "涨跌幅": [0.71, 0.82],
            "昨收": [1340.4, 12.2],
            "今开": [1345.0, 12.1],
            "最高": [1355.0, 12.4],
            "最低": [1338.0, 12.0],
            "成交量": [50000, 90000],
            "成交额": [7.2e9, 1.1e9],
        }
    )


def _df_sina_index_spot():
    return pd.DataFrame(
        {
            "代码": ["sh000001", "sz399001"],
            "名称": ["上证指数", "深证成指"],
            "最新价": [3896.49, 11000.0],
            "涨跌额": [39.69, 20.0],
            "涨跌幅": [1.02, 0.18],
            "昨收": [3856.8, 10980.0],
            "今开": [3880.0, 10990.0],
            "最高": [3940.0, 11020.0],
            "最低": [3870.0, 10970.0],
            "成交量": [1000, 2000],
            "成交额": [1e8, 2e8],
        }
    )


def _df_ths_summary():
    return pd.DataFrame(
        {
            "板块": ["半导体", "证券"],
            "涨跌幅": [1.01, -0.66],
            "总成交量": [1000, 2000],
            "总成交额": [1e8, 2e8],
            "均价": [2000.0, 1500.0],
        }
    )


def _df_ths_name():
    return pd.DataFrame({"name": ["半导体", "证券"], "code": ["881121", "881157"]})


# ---- 4.1 独立 Provider ----
def test_eastmoney_contains_no_sina_ths():
    src = inspect.getsource(EastMoneyProvider)
    assert "sina" not in src.lower() and "ths" not in src.lower()


def test_to_sina_index_mapping():
    assert to_sina_index("000001") == "sh000001"
    assert to_sina_index("399001") == "sz399001"
    assert to_sina_index("600519") == "sh600519"
    assert to_sina_index("DJI") is None


def test_sina_provider_scope_and_fetch():
    p = SinaProvider()
    p._ak = MagicMock(stock_zh_index_daily=MagicMock(return_value=_df_daily()))
    assert p.can_fetch_kline("index", "1d") is True
    assert p.can_fetch_kline("stock", "1d") is False  # 仅 A 股指数
    assert p.can_fetch_kline("index", "15m") is False
    assert p.can_fetch_realtime() is True  # 新浪实时降级源
    assert p.can_fetch_realtime_type("stock") is True
    assert p.can_fetch_realtime_type("index") is True
    assert p.can_fetch_realtime_type("industry_index") is False  # 新浪不覆盖行业指数
    # 范围外直接返回空，不调外部源
    assert (
        p.fetch_kline("600519", "1d", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC), "stock")
        == []
    )
    p._ak.stock_zh_index_daily.assert_not_called()
    # 范围内正常拉取
    bars = p.fetch_kline("000001", "1d", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC), "index")
    assert len(bars) == 2
    assert bars[0].close == 101.0 and bars[0].amount == 0.0  # 新浪指数无成交额


def test_ths_provider_scope_and_fetch():
    p = THSProvider()
    p._ak = MagicMock(stock_board_industry_index_ths=MagicMock(return_value=_df_ths()))
    assert p.can_fetch_kline("industry_index", "1d") is True
    assert p.can_fetch_kline("index", "1d") is False
    assert (
        p.fetch_kline("000001", "1d", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC), "index")
        == []
    )
    bars = p.fetch_kline(
        "半导体", "1d", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC), "industry_index"
    )
    assert len(bars) == 2 and bars[0].close == 101.0


def test_ths_provider_realtime_and_resolve():
    p = THSProvider()
    p._ak = MagicMock(
        stock_board_industry_summary_ths=MagicMock(return_value=_df_ths_summary()),
        stock_board_industry_name_ths=MagicMock(return_value=_df_ths_name()),
    )
    assert p.can_fetch_realtime() is True
    assert p.can_fetch_realtime_type("industry_index") is True
    assert p.can_fetch_realtime_type("stock") is False
    # 实时：行业板块映射（均价近似现价，无涨跌额/OHLC）
    quotes = p.fetch_realtime([RealtimeSymbol(name="半导体", asset_type="industry_index")])
    assert quotes[0].available is True
    assert quotes[0].price == 2000.0  # 均价
    assert quotes[0].change_pct == 1.01
    assert quotes[0].volume == 1000
    assert quotes[0].change is None
    # code 回填：名称 → 881xxx
    assert p.resolve_index_code("半导体") == "881121"
    assert p.resolve_index_code("不存在") is None


def test_sina_provider_realtime_stock_and_index():
    p = SinaProvider()
    p._ak = MagicMock(
        stock_zh_a_spot=MagicMock(return_value=_df_sina_spot()),
        stock_zh_index_spot_sina=MagicMock(return_value=_df_sina_index_spot()),
    )
    symbols = [
        RealtimeSymbol(code="600519", name="贵州茅台", asset_type="stock"),
        RealtimeSymbol(code="000001", name="上证指数", asset_type="index"),
        RealtimeSymbol(code="", name="半导体", asset_type="industry_index"),
    ]
    quotes = p.fetch_realtime(symbols)
    assert quotes[0].available and quotes[0].price == 1350.6  # 去 sh/sz 前缀按代码匹配
    assert quotes[1].available and quotes[1].price == 3896.49
    assert quotes[2].available is False  # 新浪不覆盖行业指数


# ---- 4.2 工厂优先级链 / 熔断 ----
class _FakeProvider(BaseDataProvider):
    """可控 fake provider：按 (name, 行为) 决定返回/抛错（不继承真实实现）。"""

    def __init__(self, name, behavior, can_kline=True, can_rt=True):
        super().__init__()
        self.name = name
        self.behavior = behavior  # "ok"/"raise"/"empty"
        self._can_kline = can_kline
        self._can_rt = can_rt
        self.calls = 0

    def can_fetch_kline(self, asset_type, period):
        return self._can_kline

    def can_fetch_realtime(self):
        return self._can_rt

    def fetch_kline(self, *a, **k):
        self.calls += 1
        if self.behavior == "raise":
            raise RuntimeError("source down")
        if self.behavior == "empty":
            return []
        return [KlineBar(ts=datetime(2026, 8, 19, tzinfo=UTC), open=1, high=2, low=1, close=1.5, volume=1, amount=1.0)]

    def fetch_realtime(self, symbols):
        self.calls += 1
        if self.behavior == "raise":
            raise RuntimeError("source down")
        return [unavailable_quote(s) for s in symbols]

    def resolve_index_code(self, name):
        return None


def _factory(*fakes, priority=None):
    f = DataProviderFactory.__new__(DataProviderFactory)
    f._providers = list(fakes)
    f._circuits = {p.name: ProviderCircuit(3, 60) for p in fakes}
    f._lock = MagicMock()
    return f


def test_factory_priority_first_success_wins():
    p1, p2 = _FakeProvider("p1", "ok"), _FakeProvider("p2", "ok")
    f = _factory(p1, p2)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    bars = f.fetch_kline("000001", "1d", start, end, "index")
    assert len(bars) == 1
    assert p1.calls == 1 and p2.calls == 0  # 第一个成功即停止


def test_factory_falls_back_on_failure():
    p1, p2 = _FakeProvider("p1", "raise"), _FakeProvider("p2", "ok")
    f = _factory(p1, p2)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    bars = f.fetch_kline("000001", "1d", start, end, "index")
    assert len(bars) == 1 and p2.calls == 1
    assert f.health()[0]["failures"] == 1


def test_factory_falls_back_on_empty_within_scope():
    p1, p2 = _FakeProvider("p1", "empty"), _FakeProvider("p2", "ok")
    f = _factory(p1, p2)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    assert len(f.fetch_kline("000001", "1d", start, end, "index")) == 1
    assert p2.calls == 1


def test_factory_scope_skips_inapplicable_provider():
    p1, p2 = _FakeProvider("p1", "ok"), _FakeProvider("p2", "ok", can_kline=False)
    f = _factory(p1, p2)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    f.fetch_kline("000001", "1d", start, end, "stock")
    assert p2.calls == 0  # 不适用直接跳过，不调用


def test_factory_circuit_opens_and_skips():
    p1, p2 = _FakeProvider("p1", "raise"), _FakeProvider("p2", "raise")
    f = _factory(p1, p2)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    for _ in range(3):
        f.fetch_kline("000001", "1d", start, end, "index")
    # p1 连续失败 3 次 → 熔断 open
    assert f.health()[0]["state"] == "open"
    calls_before = p1.calls
    f.fetch_kline("000001", "1d", start, end, "index")
    assert p1.calls == calls_before  # 熔断期内不再调用 p1
    assert f.health()[0]["cooldown_remaining"] > 0


def test_factory_half_open_recovers_on_success():
    p1 = _FakeProvider("p1", "raise")
    f = _factory(p1)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    for _ in range(3):
        f.fetch_kline("000001", "1d", start, end, "index")
    assert f.health()[0]["state"] == "open"
    # 冷却结束后半开探测：p1 恢复为 ok → 成功关闭熔断
    p1.behavior = "ok"
    circuit = f._circuits["p1"]
    circuit.cooldown_until = 0.0
    f.fetch_kline("000001", "1d", start, end, "index")
    assert f.health()[0]["state"] == "closed"
    assert f.health()[0]["last_success_at"] is not None


def test_factory_realtime_all_fail_returns_unavailable():
    p1, p2 = _FakeProvider("p1", "raise"), _FakeProvider("p2", "raise", can_rt=False)
    f = _factory(p1, p2)
    quotes = f.fetch_realtime([RealtimeSymbol(code="600519", name="贵州茅台", asset_type="stock")])
    assert len(quotes) == 1 and quotes[0].available is False  # 对齐请求契约


def test_factory_realtime_routes_per_type():
    """按资产类型分别降级：sina 覆盖 stock/index、ths 覆盖 industry_index，避免整批截断。"""

    class _StockIndexProvider(BaseDataProvider):
        name = "sina"

        def can_fetch_realtime_type(self, atype):
            return atype in ("stock", "index")

        def fetch_kline(self, *a, **k):
            return []

        def fetch_realtime(self, symbols):
            return [
                RealtimeQuote(code=s.code, name=s.name, asset_type=s.asset_type, price=1.0, available=True)
                for s in symbols
            ]

        def resolve_index_code(self, name):
            return None

    class _IndustryProvider(BaseDataProvider):
        name = "ths"

        def can_fetch_realtime_type(self, atype):
            return atype == "industry_index"

        def fetch_kline(self, *a, **k):
            return []

        def fetch_realtime(self, symbols):
            return [
                RealtimeQuote(code=s.code, name=s.name, asset_type=s.asset_type, price=2.0, available=True)
                for s in symbols
            ]

        def resolve_index_code(self, name):
            return None

    f = _factory(_StockIndexProvider(), _IndustryProvider())
    symbols = [
        RealtimeSymbol(code="600519", name="贵州茅台", asset_type="stock"),
        RealtimeSymbol(code="", name="半导体", asset_type="industry_index"),
    ]
    quotes = f.fetch_realtime(symbols)
    assert quotes[0].available and quotes[0].price == 1.0  # stock 由 sina
    assert quotes[1].available and quotes[1].price == 2.0  # industry 由 ths


def test_factory_health_shape():
    f = _factory(_FakeProvider("p1", "ok"))
    h = f.health()
    assert h[0]["name"] == "p1" and h[0]["state"] == "closed" and "failures" in h[0] and "last_success_at" in h[0]


def test_factory_probe_recovers_open_provider():
    p1, p2 = _FakeProvider("p1", "raise"), _FakeProvider("p2", "ok")
    f = _factory(p1, p2)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC)
    for _ in range(3):
        f.fetch_kline("000001", "1d", start, end, "index")
    assert f.health()[0]["state"] == "open"
    p1.behavior = "ok"
    results = f.probe()
    assert any(r["name"] == "p1" and r["recovered"] for r in results)
    assert f.health()[0]["state"] == "closed"


def test_factory_resolve_index_code_and_pe_fallthrough():
    p1 = _FakeProvider("p1", "ok")
    f = _factory(p1)
    assert f.resolve_index_code("半导体") is None
    assert f.fetch_index_pe(["沪深300"]) == {}


# ---- 配置优先级解析 ----
def test_factory_priority_config_build():
    with patch("app.data_providers.factory.get_settings") as m:
        s = m.return_value
        s.DATA_PROVIDER_PRIORITY = "sina,eastmoney"
        s.PROVIDER_CIRCUIT_FAILURE_THRESHOLD = 2
        s.PROVIDER_CIRCUIT_COOLDOWN = 5
        f = DataProviderFactory()
    names = [p.name for p in f.providers]
    assert names == ["sina", "eastmoney"]


def test_reset_provider():
    reset_provider()
    from app.data_providers.factory import get_provider

    a, b = get_provider(), get_provider()
    assert a is b  # 单例
    reset_provider()
    assert get_provider() is not a  # 重置后可重建新实例
