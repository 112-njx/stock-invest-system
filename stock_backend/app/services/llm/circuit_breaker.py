"""LLM 调用熔断器：连续失败熔断 + 冷却后半开探测。

状态机：CLOSED(正常) → OPEN(熔断，快速失败) → HALF_OPEN(冷却后放行一个探测请求)
  → 成功回 CLOSED / 失败回 OPEN。借鉴 TradingAgents-CN llm_adapters 防护思路。
"""

import threading
import time
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        """是否放行本次调用。半开状态仅放行一个探测请求（其余拒绝）。"""
        with self._lock:
            if self._state == BreakerState.CLOSED:
                return True
            if self._state == BreakerState.OPEN:
                if time.monotonic() - self._opened_at >= self.cooldown:
                    self._state = BreakerState.HALF_OPEN  # 进入半开，放行探测
                    return True
                return False
            return False  # HALF_OPEN：探测请求已放行，其余等待结果

    def on_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = BreakerState.CLOSED

    def on_failure(self) -> None:
        with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._state = BreakerState.OPEN  # 探测失败，重新熔断
                self._opened_at = time.monotonic()
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
