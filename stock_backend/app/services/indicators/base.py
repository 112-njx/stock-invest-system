"""指标基类：统一接口 `calculate(df, params) -> df`（借鉴 TradingAgents-CN tools/analysis/indicators.py）。

新指标只需继承 BaseIndicator 并注册到 indicators/__init__.py 的 INDICATORS。
"""

from abc import ABC, abstractmethod

import pandas as pd


class BaseIndicator(ABC):
    name: str = ""
    default_params: dict = {}
    required_cols: tuple[str, ...] = ()

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params, **(params or {})}

    def validate(self, df: pd.DataFrame) -> None:
        missing = [c for c in self.required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"指标 {self.name} 需要 K 线列: {missing}")

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """入参 K 线 DataFrame（含 open/high/low/close/volume/amount），返回追加指标列的 DataFrame。"""
