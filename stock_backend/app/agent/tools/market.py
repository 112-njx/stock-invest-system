"""行情工具：实时快照 / K 线。返回结构化 dict（工具内不生成自然语言，供 Agent 组织语言）。

借鉴 TradingAgents-CN tools 分层 + 详细 description 规范：description 写清何时用/怎么用/返回什么。
"""

from collections.abc import Callable

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.services import market_service


def build_market_tools(db: Session) -> list[Callable]:
    """按请求级 db 会话绑定行情工具。"""

    @tool("market_snapshot")
    def market_snapshot(symbol: str) -> dict:
        """获取指定标的（股票/ETF/指数）的实时行情快照，含最新价、涨跌幅、成交量额、换手率，以及个股总市值/PE、ETF 溢价、指数 PE 等特殊字段。

        适用于询问「当前价格/涨跌幅/市场状态」时取数；symbol 为 6 位代码（如 600519）或 symbol_id。

        Args:
            symbol: 标的代码或 symbol_id，例如 "600519"
        """
        symbol_id = market_service.resolve_symbol_id(db, symbol)
        if symbol_id is None:
            return {"error": f"标的不存在: {symbol}"}
        snaps = market_service.get_snapshots(db, [symbol_id])
        return snaps[0] if snaps else {"error": f"暂无 {symbol} 实时快照数据"}

    @tool("get_kline")
    def get_kline(symbol: str, period: str = "1d", limit: int = 60) -> dict:
        """获取标的的最近 K 线（OHLCV：开高低收/成交量/成交额），用于趋势、支撑压力、动量分析。

        周期 period: 15m（15分钟）/ 1d（日K）/ 1w（周K）/ 1mon（月K）；limit 返回最近根数（默认 60，最多 500）。

        Args:
            symbol: 标的代码或 symbol_id
            period: K线周期，15m/1d/1w/1mon
            limit: 返回最近K线根数（1-500）
        """
        if period not in ("15m", "1d", "1w", "1mon"):
            return {"error": f"不支持的周期: {period}，可选 15m/1d/1w/1mon"}
        limit = max(1, min(int(limit), 500))
        try:
            bars = market_service.get_kline(db, symbol, period, limit=limit)
        except ValueError as e:
            return {"error": str(e)}
        if not bars:
            return {"error": f"{symbol} 无 {period} K线数据（可能未同步）"}
        return {
            "symbol": symbol,
            "period": period,
            "count": len(bars),
            "bars": [
                {
                    "ts": b.ts.isoformat(),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": b.volume,
                    "amount": float(b.amount),
                }
                for b in bars[-limit:]
            ],
        }

    return [market_snapshot, get_kline]
