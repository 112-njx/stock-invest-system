"""技术指标工具：服务端计算 MACD/KDJ/成交量/成交额（前端/Agent 不计算）。"""

from collections.abc import Callable

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.services import indicator_service


def build_indicator_tools(db: Session) -> list[Callable]:
    @tool("get_indicator")
    def get_indicator(symbol: str, period: str = "1d", names: str = "macd,kdj", limit: int = 60) -> dict:
        """计算指定标的的技术指标序列（服务端计算，缓存命中直接返回）。

        指标名 names 逗号分隔，支持：macd（输出 macd_dif/macd_dea/macd_hist）、kdj（kdj_k/kdj_d/kdj_j）、
        volume（成交量）、amount（成交额）。适用于趋势/买卖点/超买超卖分析。

        Args:
            symbol: 标的代码或 symbol_id
            period: K线周期 15m/1d/1w/1mon
            names: 逗号分隔的指标名，如 "macd,kdj"
            limit: 返回最近根数（默认 60）
        """
        name_list = [n.strip() for n in names.split(",") if n.strip()]
        limit = max(1, min(int(limit), 500))
        try:
            rows = indicator_service.compute_indicators(db, symbol, period, name_list, limit=limit)
        except ValueError as e:
            return {"error": str(e)}
        if not rows:
            return {"error": f"{symbol} 无 {period} K线/指标数据"}
        return {"symbol": symbol, "period": period, "names": name_list, "count": len(rows), "rows": rows[-limit:]}

    return [get_indicator]
