"""成交量指标：数据来自 K 线 volume 列，服务端校验并透传（前端不计算）。"""

import pandas as pd

from .base import BaseIndicator


class VolumeIndicator(BaseIndicator):
    name = "volume"
    required_cols = ("volume",)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate(df)
        return df
