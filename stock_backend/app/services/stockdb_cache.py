"""Shared, versioned stockdb snapshots with background replacement and bounded response caches."""

import base64
import io
import json
import logging
from collections import OrderedDict
from hashlib import sha256
from threading import Event, Lock, Thread
from time import sleep, time
from uuid import uuid4

import numpy as np
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.services import stockdb_service as rd
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
# Include algorithm schema and source identity to isolate deployments and future calculation changes.
_namespace = "stockdb:v2:" + sha256(get_settings().STOCKDB_URL.encode()).hexdigest()[:12]
_snapshot: rd.Snapshot | None = None
_built_at = 0.0
_last_error = ""
_refresh_lock = Lock()
_schedule_lock = Lock()
_refresh_thread: Thread | None = None
_stop = Event()
_timer: Thread | None = None
_response_lock = Lock()
_responses: OrderedDict[str, bytes] = OrderedDict()
_response_bytes = 0
_RESPONSE_LIMIT = 16 * 1024 * 1024
_SHARED_TTL = 7 * 24 * 3600


def _shared_get(key: str) -> str | None:
    try:
        return get_redis_client().get(_namespace + ":" + key)
    except RedisError:
        logger.debug("stockdb shared cache read unavailable", exc_info=True)
        return None


def _pack(data: rd.Snapshot) -> str:
    metadata = json.dumps({
        "dates": data.dates, "boards": data.boards, "stocks": data.stocks,
        "positions": data.positions, "version": data.version,
    }, ensure_ascii=False, separators=(",", ":"))
    buffer = io.BytesIO()
    np.savez_compressed(buffer, metadata=np.array(metadata), values=data.values)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _unpack(encoded: str) -> rd.Snapshot:
    with np.load(io.BytesIO(base64.b64decode(encoded)), allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"]))
        return rd.Snapshot(values=archive["values"], **metadata)


def _restore(state: dict) -> bool:
    global _snapshot, _built_at
    if _snapshot is not None and _snapshot.version == state["version"]:
        _built_at = state["built_at"]
        return True
    encoded = _shared_get("snapshot:" + state["version"])
    if encoded is None:
        return False
    try:
        restored = _unpack(encoded)
    except Exception:
        logger.warning("stockdb persisted snapshot is invalid; rebuilding", exc_info=True)
        return False
    if restored.version != state["version"]:
        return False
    _snapshot = restored
    _built_at = state["built_at"]
    return True


def _state() -> dict | None:
    try:
        raw = _shared_get("state")
        state = json.loads(raw) if raw else None
        if isinstance(state, dict) and isinstance(state.get("version"), str) and isinstance(
            state.get("built_at"), (int, float),
        ):
            return state
        return None
    except (ValueError, KeyError, TypeError):
        return None


def _rebuild(force: bool = False) -> None:
    global _snapshot, _built_at, _last_error
    if not _refresh_lock.acquire(blocking=False):
        return
    redis = get_redis_client()
    token = str(uuid4())
    owns_lease = False
    try:
        state = _state()
        restored = bool(state and _restore(state))
        if restored and not force and time() - state["built_at"] < rd.CACHE_SECONDS:
            warm_home(_snapshot)
            _last_error = ""
            return
        try:
            owns_lease = bool(redis.set(_namespace + ":building", token, nx=True, ex=300))
            if not owns_lease:
                if state:
                    _restore(state)
                return
        except RedisError:
            # A local snapshot remains available if the shared cache is temporarily offline.
            logger.debug("stockdb refresh lease unavailable", exc_info=True)
        candidate = rd._load_snapshot()
        built_at = time()
        # Warm only the default first screen, before publishing a new generation.
        warm_home(candidate)
        if owns_lease:
            # Publish the blob before its pointer. Readers always observe a complete generation.
            snapshot_key = _namespace + ":snapshot:" + candidate.version
            if not state or state["version"] != candidate.version or not redis.exists(snapshot_key):
                redis.set(snapshot_key, _pack(candidate), ex=_SHARED_TTL)
            else:
                redis.expire(snapshot_key, _SHARED_TTL)
            previous = state.get("previous") if state and state["version"] == candidate.version else (
                state["version"] if state else None
            )
            state_json = json.dumps({"version": candidate.version, "built_at": built_at, "previous": previous})
            published = redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "redis.call('set', KEYS[2], ARGV[2], 'EX', ARGV[3]); return 1 end; return 0",
                2, _namespace + ":building", _namespace + ":state", token, state_json, _SHARED_TTL,
            )
            if not published:
                return
            if state and state["version"] != candidate.version and state.get("previous") not in (
                None, candidate.version, previous,
            ):
                redis.delete(_namespace + ":snapshot:" + state["previous"])
        if _snapshot is None or _snapshot.version != candidate.version:
            _snapshot = candidate
        _built_at = built_at
        _last_error = ""
    except Exception as exc:  # The last complete generation survives a failed refresh.
        _last_error = str(exc)
        logger.warning("stockdb snapshot refresh failed: %s", exc)
    finally:
        if owns_lease:
            try:
                redis.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end; return 0",
                    1, _namespace + ":building", token,
                )
            except RedisError:
                logger.debug("stockdb refresh lease cleanup unavailable", exc_info=True)
        _refresh_lock.release()


def refresh(force: bool = False) -> None:
    global _refresh_thread
    with _schedule_lock:
        if _refresh_thread is not None and _refresh_thread.is_alive():
            return
        _refresh_thread = Thread(target=_rebuild, args=(force,), name="stockdb-refresh", daemon=True)
        _refresh_thread.start()


def get_snapshot() -> rd.Snapshot:
    if _snapshot is None:
        # Normally populated by startup. This also supports standalone callers and tests.
        _rebuild()
    if _snapshot is None:
        raise rd.StockDBError(_last_error or "本地数据正在准备，请稍后重试。")
    if time() - _built_at >= rd.CACHE_SECONDS:
        refresh()
    return _snapshot


def status() -> dict:
    return {
        "version": _snapshot.version if _snapshot else None,
        "refreshing": _refresh_lock.locked() or bool(_shared_get("building")),
        "error": _last_error,
    }


def prepare() -> None:
    state = _state()
    if state and _restore(state):
        warm_home(_snapshot)
        if time() - state["built_at"] >= rd.CACHE_SECONDS:
            refresh()
        return
    _rebuild()
    # Other API processes may be constructing the first shared generation.
    for _ in range(150):
        if _snapshot is not None or not _shared_get("building"):
            return
        sleep(0.2)
        state = _state()
        if state and _restore(state):
            return


def start() -> None:
    global _timer
    if _timer is not None and _timer.is_alive():
        return
    _stop.clear()

    def run():
        while not _stop.wait(15):
            _rebuild()

    _timer = Thread(target=run, name="stockdb-cache", daemon=True)
    _timer.start()


def stop() -> None:
    _stop.set()


def response_bytes(data: rd.Snapshot, key: str, build) -> bytes:
    """Cache encoded JSON, avoiding recursive FastAPI encoding on cache hits."""
    global _response_bytes
    identity = data.version + ":" + key
    with _response_lock:
        saved = _responses.get(identity)
        if saved is not None:
            _responses.move_to_end(identity)
            return saved
    shared_key = "response:" + sha256(identity.encode()).hexdigest()
    shared = _shared_get(shared_key)
    encoded = shared.encode() if shared is not None else json.dumps(
        build(), ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode()
    if shared is None and len(encoded) <= 1024 * 1024:
        try:
            get_redis_client().eval(
                "redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[2]); "
                "redis.call('zadd', KEYS[2], ARGV[3], KEYS[1]); "
                "local old = redis.call('zrange', KEYS[2], 0, -257); "
                "for _, key in ipairs(old) do redis.call('del', key); redis.call('zrem', KEYS[2], key) end; "
                "redis.call('expire', KEYS[2], ARGV[2]); return 1",
                2, _namespace + ":" + shared_key, _namespace + ":responses",
                encoded.decode(), _SHARED_TTL, time(),
            )
        except RedisError:
            logger.debug("stockdb response cache write unavailable", exc_info=True)
    with _response_lock:
        previous = _responses.pop(identity, None)
        if previous is not None:
            _response_bytes -= len(previous)
        if len(encoded) <= _RESPONSE_LIMIT:
            _responses[identity] = encoded
            _response_bytes += len(encoded)
        while _response_bytes > _RESPONSE_LIMIT or len(_responses) > 256:
            _, removed = _responses.popitem(last=False)
            _response_bytes -= len(removed)
    return encoded


def changes(bars: list) -> dict:
    latest = bars[-1] if bars else None
    result = {}
    for days in (1, 3, 5, 10, 15, 30):
        previous = bars[-days - 1][4] if len(bars) > days else (latest[7] if latest and days == 1 else 0)
        result[str(days)] = (latest[4] / previous - 1) * 100 if latest and previous else None
    return result


def ranking(data: rd.Snapshot, category: str, weight: str) -> list:
    return [
        {"id": board["id"], "name": board["name"], "count": board["count"],
         "price": board["bars"][-1][4] if board["bars"] else None, "changes": changes(board["bars"])}
        for board in data.category(category, weight)
    ]


def member_bundle(data: rd.Snapshot, codes: list[str], selected: str = "",
                  order: str = "return", ascending: bool = False) -> dict:
    members = data.members(codes)
    def member_key(stock):
        if order == "code":
            return stock["code"]
        if order == "price":
            return stock["bar"][4]
        return changes([stock["bar"]])["1"] or 0

    ordered = sorted(members, key=lambda stock: stock["code"])
    ordered.sort(key=member_key, reverse=not ascending)
    available = {stock["code"] for stock in members}
    selected = selected if selected in available else (ordered[0]["code"] if ordered else "")
    return {
        "members": members, "count": len(codes), "stockCode": selected,
        "stockBars": data.stocks[selected]["bars"] if selected else [],
    }


def home(data: rd.Snapshot) -> dict:
    boards = ranking(data, "sw1", "equal")
    first = sorted(boards, key=lambda board: (-(board["price"] or 0), board["id"]))[:10]
    selected = first[0]["id"] if first else ""
    curves = {board["id"]: board["bars"] for board in data.category("sw1", "equal") if board["id"] in {b["id"] for b in first}}
    bundle = member_bundle(data, data.boards[selected]["symbols"]) if selected else {
        "members": [], "count": 0, "stockCode": "", "stockBars": [],
    }
    return {"version": data.version, "date": data.dates[-1], "boards": boards,
            "charts": curves, "boardId": selected, "detail": bundle}


def warm_home(data: rd.Snapshot) -> None:
    response_bytes(data, "home", lambda: home(data))
