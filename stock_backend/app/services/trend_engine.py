"""Causal, close-to-close swing states. No historical labels are rewritten."""

from dataclasses import dataclass, field


@dataclass
class TrendState:
    close: float = 0.0
    date: int = 0
    direction: int = 0
    age: int = 0
    pending: int = 0
    pending_days: int = 0
    base: float = 0.0
    base_date: int = 0
    fast: float = 0.0
    slow: float = 0.0
    dea: float = 0.0
    cross: bool = False
    volumes: list[float] = field(default_factory=list)

    def advance(self, date: int, close: float, volume: float, change: float) -> dict:
        if date <= self.date or close <= 0:
            raise ValueError("Trend bars must have increasing dates and positive adjusted closes")
        previous = self.close
        old_gap = self.fast - self.slow - self.dea
        self.fast = close if not previous else self.fast + (close - self.fast) * 2 / 13
        self.slow = close if not previous else self.slow + (close - self.slow) * 2 / 27
        dif = self.fast - self.slow
        self.dea += (dif - self.dea) * 2 / 10
        self.cross = bool(previous and old_gap <= 0 < dif - self.dea)
        # Tolerate floating-point noise from corporate-action factors.
        tolerance = max(abs(close), abs(previous)) * 1e-10
        sign = (1 if close > previous + tolerance else -1 if close < previous - tolerance else 0) if previous else 0
        if self.direction:
            self.age += 1
        if sign and sign != self.direction:
            self.pending_days = self.pending_days + 1 if self.pending == sign else 1
            self.pending = sign
            if self.pending_days == 2:
                self.direction, self.age = sign, 1
                self.base, self.base_date = previous, self.date
                self.pending, self.pending_days = 0, 0
        else:
            self.pending, self.pending_days = 0, 0
        signals = ""
        if self.direction > 0 and self.age == 2:
            signals += "B"
        if self.direction < 0 and self.age == 1:
            signals += "S"
        if self.direction > 0 and change > 0 and len(self.volumes) == 20 and volume > max(self.volumes):
            signals += "V"
        self.volumes = (self.volumes + [max(0, volume)])[-20:]
        self.close, self.date = close, date
        return {"wave": self.direction * self.age, "change": change, "signals": signals}

    def metrics(self, latest_factor: float) -> dict:
        dif = (self.fast - self.slow) / latest_factor
        dea = self.dea / latest_factor
        return {
            "wave": self.direction * self.age,
            "return": (self.close / self.base - 1) * 100 if self.base else None,
            "baseDate": self.base_date or None, "quoteDate": self.date,
            "dif": dif, "dea": dea, "macd": 2 * (dif - dea), "cross": self.cross,
        }
