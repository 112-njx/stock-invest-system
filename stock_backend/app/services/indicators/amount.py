"""成交额指标：数据来自 K 线 amount 列，服务端校验并透传（前端不计算）。"""

import pandas as pd

from .base import BaseIndicator


class AmountIndicator(BaseIndicator):
    name = "amount"
    required_cols = ("amount",)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate(df)
        return df
