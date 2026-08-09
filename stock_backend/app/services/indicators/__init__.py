"""指标注册表：新增指标只需加一个类并在此登记（预留 RSI/布林带/ATR 位置）。"""

from .amount import AmountIndicator
from .base import BaseIndicator
from .kdj import KDJIndicator
from .macd import MACDIndicator
from .volume import VolumeIndicator

INDICATORS: dict[str, type[BaseIndicator]] = {
    "macd": MACDIndicator,
    "kdj": KDJIndicator,
    "volume": VolumeIndicator,
    "amount": AmountIndicator,
}

__all__ = ["BaseIndicator", "INDICATORS"]


def get_indicator(name: str, params: dict | None = None) -> BaseIndicator:
    cls = INDICATORS.get(name.lower())
    if cls is None:
        raise ValueError(f"unsupported indicator: {name}")
    return cls(params)
