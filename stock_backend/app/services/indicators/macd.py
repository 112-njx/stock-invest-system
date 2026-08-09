"""MACD 指标：DIF = EMA(fast) - EMA(slow)，DEA = EMA(DIF)，柱 = 2*(DIF-DEA)（A股惯例，同花顺/通达信）。"""

import pandas as pd

from .base import BaseIndicator


class MACDIndicator(BaseIndicator):
    name = "macd"
    default_params = {"fast": 12, "slow": 26, "signal": 9}
    required_cols = ("close",)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate(df)
        close = df["close"]
        fast = self.params["fast"]
        slow = self.params["slow"]
        signal = self.params["signal"]
        dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
        dea = dif.ewm(span=signal, adjust=False).mean()
        out = df.copy()
        out["macd_dif"] = dif
        out["macd_dea"] = dea
        out["macd_hist"] = (dif - dea) * 2  # 柱 ×2 与国内行情软件一致
        return out
