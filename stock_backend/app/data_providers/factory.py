"""数据源工厂：优先级链 + 独立熔断（行情源可插拔）。

- 有序 Provider 链（默认 eastmoney → sina → ths），顺序/启用由 `DATA_PROVIDER_PRIORITY` 配置。
- 每个 Provider 独立熔断：连续失败 N 次熔断 M 秒，熔断期内跳过，半开探测自动恢复，互不影响。
- 业务代码仍通过 `get_provider()` 获取工厂实例，`fetch_kline/fetch_realtime/resolve_index_code/fetch_index_pe`
  调用方式与单 Provider 一致，不影响现有同步链路。
"""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings

from .base import BaseDataProvider, unavailable_quote
from .eastmoney import EastMoneyProvider
from .sina import SinaProvider
from .ths import THSProvider

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, type[BaseDataProvider]] = {
    "eastmoney": EastMoneyProvider,
    "sina": SinaProvider,
    "ths": THSProvider,
}


class ProviderCircuit:
    """单个 Provider 的熔断状态机（closed / open / half_open）。"""

    def __init__(self, failure_threshold: int, cooldown: float) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.failures = 0
        self.state = "closed"
        self.cooldown_until = 0.0
        self.last_success_at: datetime | None = None

    def allow(self, now: float) -> bool:
        if self.state == "open":
            if now >= self.cooldown_until:
                self.state = "half_open"  # 半开探测：放行一次请求验证是否恢复
                return True
            return False
        return True

    def record_success(self, now: float) -> None:
        self.failures = 0
        self.state = "closed"
        self.last_success_at = datetime.now(UTC)

    def record_failure(self, now: float) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.cooldown_until = now + self.cooldown


class DataProviderFactory:
    """优先级链工厂：按序尝试 Provider，第一个成功返回即停止；全部失败返回空结果。"""

    def __init__(self, priority: str | None = None) -> None:
        settings = get_settings()
        names = [n.strip() for n in (priority or settings.DATA_PROVIDER_PRIORITY).split(",") if n.strip()]
        self._providers: list[BaseDataProvider] = [
            PROVIDER_REGISTRY[name]() for name in names if name in PROVIDER_REGISTRY
        ]
        self._circuits: dict[str, ProviderCircuit] = {
            p.name: ProviderCircuit(settings.PROVIDER_CIRCUIT_FAILURE_THRESHOLD, settings.PROVIDER_CIRCUIT_COOLDOWN)
            for p in self._providers
        }
        self._lock = threading.Lock()

    @property
    def providers(self) -> list[BaseDataProvider]:
        return list(self._providers)

    def _iter_chain(self, method: str, args: tuple, kwargs: dict, scope) -> object | None:
        """按优先级遍历 Provider 执行 method，返回第一个非空结果；熔断/异常自动切下一个。"""
        now = time.time()
        for p in self._providers:
            if scope and not scope(p):
                continue
            circuit = self._circuits[p.name]
            with self._lock:
                allow = circuit.allow(now)
            if not allow:
                logger.info("[provider] %s open (cooldown %ds), skip", p.name, int(circuit.cooldown_until - now))
                continue
            try:
                result = getattr(p, method)(*args, **kwargs)
                if result:
                    with self._lock:
                        circuit.record_success(now)
                    return result
                logger.warning("[provider] %s empty, fallback to next", p.name)
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    circuit.record_failure(now)
                logger.warning(
                    "[provider] %s failed (%s), fallback to next",
                    p.name,
                    str(exc)[:120],
                    exc_info=False,
                )
        return None

    # ---- 对外接口（与单 Provider 一致，业务代码调用方式不变）----
    def fetch_kline(
        self,
        symbol: str,
        period: str,
        start,
        end,
        asset_type: str = "stock",
    ) -> list:
        result = self._iter_chain(
            "fetch_kline",
            (symbol, period, start, end, asset_type),
            {},
            scope=lambda p: p.can_fetch_kline(asset_type, period),
        )
        return result or []

    def fetch_realtime(self, symbols) -> list:
        result = self._iter_chain("fetch_realtime", (symbols,), {}, scope=lambda p: p.can_fetch_realtime())
        if result:
            return result
        # 全部失败：返回对齐请求的不可用快照，保持调用方 zip 对齐契约（run_realtime_poll 不抛错）
        return [unavailable_quote(s) for s in symbols]

    def resolve_index_code(self, name: str) -> str | None:
        """行业指数名称 → 板块代码（best-effort，仅东方财富提供）。"""
        for p in self._providers:
            try:
                code = p.resolve_index_code(name)
                if code:
                    return code
            except Exception:  # noqa: BLE001
                continue
        return None

    def fetch_catalog(self) -> dict:
        """全量标的目录（仅东方财富提供）：{stocks: [(code,name)], etfs: [(code,name)]}。"""
        for p in self._providers:
            fn = getattr(p, "fetch_catalog", None)
            if fn is None:
                continue
            try:
                result = fn()
                if result and (result.get("stocks") or result.get("etfs")):
                    return result
            except Exception:  # noqa: BLE001
                continue
        return {"stocks": [], "etfs": []}

    def search_ak_stock(self, keyword: str, limit: int = 10) -> list[tuple[str, str]]:
        """外部搜索回退：仅东方财富提供，失败返回空。"""
        for p in self._providers:
            fn = getattr(p, "search_ak_stock", None)
            if fn is None:
                continue
            try:
                result = fn(keyword, limit)
                if result:
                    return result
            except Exception:  # noqa: BLE001
                continue
        return []

    def fetch_index_pe(self, names: list[str]) -> dict:
        """指数 PE（best-effort，仅东方财富提供，失败静默跳过）。"""
        for p in self._providers:
            fn = getattr(p, "fetch_index_pe", None)
            if fn is None:
                continue
            try:
                result = fn(names)
                if result:
                    return result
            except Exception:  # noqa: BLE001
                continue
        return {}

    # ---- 健康检查 / 熔断探测 ----
    def health(self) -> list[dict]:
        now = time.time()
        out: list[dict] = []
        for p in self._providers:
            c = self._circuits[p.name]
            out.append(
                {
                    "name": p.name,
                    "state": c.state,
                    "failures": c.failures,
                    "last_success_at": c.last_success_at.isoformat() if c.last_success_at else None,
                    "cooldown_remaining": max(0, int(c.cooldown_until - now)) if c.state == "open" else 0,
                }
            )
        return out

    def probe(self) -> list[dict]:
        """探测熔断中的 Provider（取固定标的 1 根日K），成功即恢复。返回本次探测结果。"""
        now = time.time()
        results: list[dict] = []
        for p in self._providers:
            c = self._circuits[p.name]
            if c.state != "open":
                continue
            try:
                end = datetime.now(UTC)
                start = end - timedelta(days=5)
                bars = p.fetch_kline(p.probe_symbol, "1d", start, end, p.probe_asset_type)
                recovered = bool(bars)
            except Exception:  # noqa: BLE001
                recovered = False
            if recovered:
                with self._lock:
                    c.record_success(now)
            results.append({"name": p.name, "state": c.state if not recovered else "closed", "recovered": recovered})
        return results


_factory: DataProviderFactory | None = None


def get_provider() -> DataProviderFactory:
    """获取全局 DataProvider 工厂（懒加载单例）。"""
    global _factory
    if _factory is None:
        _factory = DataProviderFactory()
    return _factory


def reset_provider() -> None:
    """重置工厂单例（测试隔离用）。"""
    global _factory
    _factory = None
