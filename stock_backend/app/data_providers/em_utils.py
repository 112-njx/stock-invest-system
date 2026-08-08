"""东方财富反爬防护：requests 补丁（借鉴 TradingAgents-CN akshare 提供器）。

将 eastmoney.com 的全部 HTTP 请求改用 curl_cffi 模拟 Chrome TLS 指纹，
并做同域请求间隔节流，避免被反爬断连。补丁打在 requests.Session.request，
覆盖 akshare 内部 requests.get 与 requests.Session().get 两条路径。
"""

import logging
import threading
import time

import requests
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

_PATCHED = False
_MIN_INTERVAL = 0.6  # 同域请求最小间隔（秒）
_last_request_time = 0.0
_lock = threading.Lock()

# curl_cffi 可透传的 kwargs（避免不兼容参数导致请求失败）
_PASS_KEYS = ("params", "data", "json", "headers", "timeout", "cookies", "allow_redirects", "verify")


def _throttle() -> None:
    global _last_request_time
    with _lock:
        now = time.time()
        gap = now - _last_request_time
        if gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        _last_request_time = time.time()


def install_requests_patch() -> None:
    """幂等安装补丁：所有 eastmoney.com 请求走 curl_cffi。"""
    global _PATCHED
    if _PATCHED:
        return

    _orig_request = requests.sessions.Session.request

    def _patched_request(self, method, url, **kwargs):
        if "eastmoney.com" in str(url):
            _throttle()
            try:
                keep = {k: v for k, v in kwargs.items() if k in _PASS_KEYS}
                return curl_requests.request(method, url, impersonate="chrome120", **keep)
            except Exception:
                logger.debug("curl_cffi request failed, fallback to requests", exc_info=True)
        return _orig_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _patched_request
    _PATCHED = True
