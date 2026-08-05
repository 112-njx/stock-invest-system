"""Retry decorators built on tenacity."""

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    before_sleep_log,
)
import logging

from src.common.errors import AkshareUpstreamError, WriterError

_stdlib_logger = logging.getLogger("retry")


akshare_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((AkshareUpstreamError, ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
)


db_retry = retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_fixed(0.5),
    retry=retry_if_exception_type(WriterError),
    before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
)
