"""Read-only bounded probes for the local market services; never fetch external data."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings


def _probe(url: str, params: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        if params is None:
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                return {"state": "unavailable", "latest_date": None}
            return {"state": "online", "latest_date": None}
        if not isinstance(payload, list):
            return {"state": "unavailable", "latest_date": None}
        day = payload[-1].rsplit(":", 1)[-1] if payload else None
        if day:
            datetime.strptime(day, "%Y%m%d")
        return {"state": "online", "latest_date": day}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {"state": "unavailable", "latest_date": None}


def local_service_status() -> dict:
    settings = get_settings()
    with ThreadPoolExecutor(max_workers=2) as pool:
        stockdb = pool.submit(_probe, settings.STOCKDB_URL.rstrip('/') + '/', {
            "cmd": "keys", "t": "日k", "k1": "key:600519", "k2": "all:", "num": -1, "json": 1,
        })
        sdk = pool.submit(_probe, settings.STOCKDB_SDK_URL.rstrip('/') + '/health')
        return {"stockdb": stockdb.result(), "sdk": sdk.result(),
                "date_scope": "600519", "observed_at": datetime.now(UTC).isoformat()}
