"""Local StockDB history and catalog adapter. Prices use the SDK's qfq convention."""

import logging
import math
import re
from bisect import bisect_right
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings
from .base import BaseDataProvider, KlineBar, ProviderError, unavailable_quote

logger = logging.getLogger(__name__)


class StockDBProvider(BaseDataProvider):
    name = "stockdb"
    probe_symbol = "600519"
    probe_asset_type = "stock"

    def query(self, command: str, table: str, **params):
        try:
            with httpx.Client(base_url=get_settings().STOCKDB_URL, timeout=self.timeout, trust_env=False) as client:
                response = client.get("/", params={"cmd": command, "t": table, "json": 1, **params})
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, (list, dict)):
                raise ValueError("unexpected RD response")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[stockdb] connection_or_response_error table=%s: %s", table, exc)
            raise ProviderError(f"StockDB 本地查询失败: {exc}") from exc

    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        # Bare index codes collide with stock codes in the local dataset.
        if asset_type == 'sw_index' and period == '15m':
            return False
        return asset_type in {"stock", "etf", "sw_index"} and period in {"1d", "15m", "1w", "1mon"}

    def can_fetch_realtime(self) -> bool:
        return False

    def fetch_realtime(self, symbols):
        return [unavailable_quote(symbol) for symbol in symbols]

    def resolve_index_code(self, name: str) -> str | None:
        return None

    def latest_day(self, code: str = "600519"):
        keys = self.query("keys", "日k", k1=f"key:{code}", k2="all:", num=-1)
        return datetime.strptime(keys[-1].rsplit(":", 1)[-1], "%Y%m%d").date() if keys else None

    def refresh_sdk(self):
        try:
            with httpx.Client(timeout=180, trust_env=False) as client:
                response = client.post(get_settings().STOCKDB_SDK_URL.rstrip('/') + '/refresh')
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f'Free-StockDB SDK 服务不可用: {exc}') from exc

    def fetch_kline(self, symbol, period, start, end, asset_type="stock") -> list[KlineBar]:
        if self.can_fetch_kline(asset_type, period) and (period in {"1w", "1mon"} or asset_type == "sw_index"):
            return self._sdk_kline(symbol, period, start, end)
        if not self.can_fetch_kline(asset_type, period) or not re.fullmatch(r"\d{6}", symbol):
            return []
        settings = get_settings()
        local_start, local_end = start.astimezone(settings.tz), end.astimezone(settings.tz)
        first_day, last_day = local_start.date(), local_end.date()
        if period == "1d":
            first_day, last_day = start.astimezone(UTC).date(), end.astimezone(UTC).date()
        factors = self.query("get", "复权", k1=f"key:{symbol}", k2="all:")
        timeline = sorted((int(key.rsplit(":", 1)[-1]), float(value["cum"])) for key, value in factors)
        factor_dates = [date for date, _ in timeline]
        latest_factor = timeline[-1][1] if timeline else 1.0
        output = []
        cursor = first_day
        while cursor <= last_day:
            last = min(cursor + timedelta(days=29), last_day)
            first_key, last_key = cursor.strftime("%Y%m%d"), last.strftime("%Y%m%d")
            table = "日k" if period == "1d" else "分钟k"
            if period == "15m":
                first_key += "000000"
                last_key += "235959"
            records = self.query("vals", table, k1=f"key:{symbol}", k2=f"fwd:{first_key},{last_key}")
            adjusted = []
            for record in records:
                if record.get("code") != symbol:
                    raise ProviderError("StockDB 返回标的代码不匹配")
                date = int(str(record["date"])[:8])
                offset = bisect_right(factor_dates, date)
                factor = timeline[offset - 1][1] if offset else 1.0
                ratio = factor / latest_factor
                row = dict(record)
                for field in ("open", "high", "low", "close"):
                    value = float(row[field])
                    row[field] = round(value * ratio, 3 if asset_type == "etf" else 2) if abs(ratio - 1) >= 1e-6 else value
                    if not math.isfinite(row[field]):
                        raise ProviderError("StockDB 返回无效价格")
                adjusted.append(row)
            if period == "15m":
                adjusted = self._aggregate_minutes(adjusted)
            for row in adjusted:
                stamp = str(row["date"])
                ts = datetime.strptime(stamp, "%Y%m%d" if period == "1d" else "%Y%m%d%H%M%S")
                # Existing daily tables label sessions with UTC midnight.
                ts = ts.replace(tzinfo=UTC if period == "1d" else settings.tz).astimezone(UTC)
                in_range = first_day <= ts.date() <= last_day if period == "1d" else start <= ts <= end
                if in_range:
                    # Existing AkShare stock/ETF K-lines store volume in lots (100 shares/units).
                    volume = int(row.get("volume") or 0) // 100
                    output.append(KlineBar(ts, row["open"], row["high"], row["low"], row["close"],
                                           volume, float(row.get("amount") or 0)))
            cursor = last + timedelta(days=1)
        if not output:
            logger.info("[stockdb] coverage_empty code=%s period=%s start=%s end=%s", symbol, period, start, end)
        return sorted(output, key=lambda bar: bar.ts)

    def _sdk_kline(self, symbol, period, start, end):
        settings = get_settings()
        frequency = "1M" if period == "1mon" else period
        # Ask the SDK for complete containing periods, then filter by returned labels.
        first = start.astimezone(UTC).date()
        if period == "1w":
            first -= timedelta(days=first.weekday())
        elif period == "1mon":
            first = first.replace(day=1)
        try:
            with httpx.Client(timeout=180, trust_env=False) as client:
                response = client.get(settings.STOCKDB_SDK_URL.rstrip("/") + "/kline", params={
                    "code": symbol, "frequency": frequency, "start": first.strftime("%Y%m%d"),
                    "end": end.astimezone(settings.tz).strftime("%Y%m%d"),
                })
                response.raise_for_status()
                rows = response.json()
            if not isinstance(rows, list):
                raise ValueError("invalid SDK result")
            bars = []
            for row in rows:
                stamp = str(row['date'])
                ts = datetime.strptime(stamp, '%Y%m%d%H%M%S' if len(stamp) == 14 else '%Y%m%d')
                ts = ts.replace(tzinfo=settings.tz if len(stamp) == 14 else UTC).astimezone(UTC)
                if start <= ts <= end:
                    bars.append(KlineBar(ts, *[float(row[f]) for f in ('open','high','low','close')],
                                         int(row.get('volume') or 0) // 100, float(row.get('amount') or 0)))
            return bars
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError(f"Free-StockDB SDK 查询失败: {exc}") from exc

    @staticmethod
    def _aggregate_minutes(records):
        groups = defaultdict(list)
        for row in sorted(records, key=lambda row: row["date"]):
            stamp = str(row["date"])
            minute = int(stamp[8:10]) * 60 + int(stamp[10:12])
            if 570 <= minute <= 690:
                elapsed = minute - 570
            elif 780 <= minute <= 900:
                elapsed = max(121, minute - 780 + 120)
            else:
                continue
            end = max(15, ((elapsed - 1) // 15 + 1) * 15)
            groups[(stamp[:8], end)].append(row)
        output = []
        for (day, elapsed), rows in sorted(groups.items()):
            minute = 570 + elapsed if elapsed <= 120 else 780 + elapsed - 120
            output.append({"date": int(f"{day}{minute // 60:02d}{minute % 60:02d}00"),
                           "open": rows[0]["open"], "close": rows[-1]["close"],
                           "high": max(row["high"] for row in rows), "low": min(row["low"] for row in rows),
                           "volume": sum(row.get("volume") or 0 for row in rows),
                           "amount": sum(row.get("amount") or 0 for row in rows)})
        return output

    def fetch_catalog(self) -> dict:
        directory = self.query("get", "股票代码")
        if not directory:
            return {}
        codes = {str(code) for values in directory.values() for code in values}
        latest = self.latest_day()
        if latest is None:
            return {}
        rows = self.query("vals", "日k", k1="all:", k2=f"key:{latest:%Y%m%d}", ap="get.code,name")
        names = dict(rows)
        stocks, etfs = [], []
        for code in sorted(codes):
            stock = code.startswith(("60", "68", "00", "30", "920", "43", "83", "87"))
            etf = code.startswith(("51", "56", "58", "15"))
            if not stock and not etf:
                continue
            if code not in names:
                last = self.query("vals", "日k", k1=f"key:{code}", k2="all:", num=-1, ap="get.code,name")
                if last:
                    names[code] = last[-1][1]
            if code in names:
                (stocks if stock else etfs).append((code, names[code]))
        return {"stocks": stocks, "etfs": etfs}
