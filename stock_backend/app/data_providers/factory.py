"""数据源工厂：行情提供器可插拔（默认东方财富，可按配置扩展供应商）。"""

from app.core.config import get_settings

from .base import BaseDataProvider
from .eastmoney import EastMoneyProvider

_PROVIDERS: dict[str, type[BaseDataProvider]] = {"eastmoney": EastMoneyProvider}
_provider: BaseDataProvider | None = None


def get_provider() -> BaseDataProvider:
    global _provider
    if _provider is None:
        name = get_settings().DATA_PROVIDER
        cls = _PROVIDERS.get(name, EastMoneyProvider)
        _provider = cls()
    return _provider
