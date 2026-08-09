"""KDJ 指标：RSV 归一化 → K/D 递推（初值 50，经典公式）→ J = 3K - 2D。"""

import numpy as np
import pandas as pd

from .base import BaseIndicator


class KDJIndicator(BaseIndicator):
    name = "kdj"
    default_params = {"n": 9, "m1": 3, "m2": 3}
    required_cols = ("high", "low", "close")

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate(df)
        n = self.params["n"]
        m1 = self.params["m1"]
        m2 = self.params["m2"]
        lowest = df["low"].rolling(n, min_periods=n).min()
        highest = df["high"].rolling(n, min_periods=n).max()
        rsv = (df["close"] - lowest) / (highest - lowest) * 100
        rsv = rsv.replace([np.inf, -np.inf], np.nan)

        k = np.full(len(df), np.nan)
        d = np.full(len(df), np.nan)
        prev_k = prev_d = 50.0
        for i in range(len(df)):
            rv = rsv.iloc[i]
            if pd.isna(rv):
                continue
            prev_k = (1 - 1 / m1) * prev_k + rv / m1
            prev_d = (1 - 1 / m2) * prev_d + prev_k / m2
            k[i] = prev_k
            d[i] = prev_d
        out = df.copy()
        out["kdj_k"] = k
        out["kdj_d"] = d
        out["kdj_j"] = 3 * k - 2 * d
        return out
