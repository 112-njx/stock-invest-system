"""Persist forecast inputs, dispatch work, and advance opt-in tracking cursors."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from time import monotonic

from sqlalchemy import String, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import load_only

from app.core.exceptions import ApiError
from app.models.forecast import ForecastRun, ForecastTracking
from app.models.user import User
from app.services import forecast_analysis, forecast_snapshot
from app.services.llm.llm_service import LLMError, classify_llm_error
from app.services.llm.user_key import build_llm_service_for_user
from app.utils.db import get_session

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "diagnosing", "predicting")
TRACK_LIMIT = 10
SWEEP_LIMIT = 25
DELIVERY_RETRY = timedelta(minutes=1)
DELIVERY_LIFETIME = timedelta(hours=2)
TRACK_INTERVAL = timedelta(minutes=5)
TRACK_LEASE = timedelta(seconds=75)
TRACK_START_BUDGET = 8  # Leave time for a 45-second SDK request within the sweep limit.


def _lock_user(db, user_id):
    db.execute(select(func.pg_advisory_xact_lock(36236, user_id)))


def as_response(run):
    return {
        "id": run.id,
        "symbol": run.symbol,
        "trigger": run.trigger,
        "status": run.status,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "snapshot": {key: value for key, value in run.snapshot.items() if key != "rows"},
        "diagnosis": run.diagnosis,
        "prediction": run.prediction,
        "models": run.models,
        "error": run.error,
    }


def history(db, user_id, symbol):
    # Progress polls return metadata and results, without transferring archived bars.
    metadata = ForecastRun.snapshot.op("-", return_type=JSONB)(literal("rows", String)).label("snapshot")
    runs = db.execute(select(
        ForecastRun.id, ForecastRun.symbol, ForecastRun.trigger, ForecastRun.status,
        ForecastRun.created_at, ForecastRun.updated_at, metadata, ForecastRun.diagnosis,
        ForecastRun.prediction, ForecastRun.models, ForecastRun.error,
    ).where(ForecastRun.user_id == user_id, ForecastRun.symbol == symbol)
        .order_by(ForecastRun.id.desc()).limit(20)).all()
    return {
        "runs": [as_response(run) for run in runs],
        "tracking": db.get(ForecastTracking, (user_id, symbol)) is not None,
    }


def set_tracking(db, user_id, symbol, enabled):
    _lock_user(db, user_id)
    existing = db.get(ForecastTracking, (user_id, symbol))
    if enabled and existing is None:
        stock = forecast_snapshot.resolve_stock(db, symbol)
        count = db.scalar(select(func.count()).select_from(ForecastTracking).where(ForecastTracking.user_id == user_id))
        if count >= TRACK_LIMIT:
            raise ApiError(status_code=409, msg=f"最多自动跟踪 {TRACK_LIMIT} 只股票")
        latest = forecast_snapshot.latest_confirmed_session(db, stock.id, datetime.now(UTC))
        db.add(ForecastTracking(user_id=user_id, symbol=symbol, last_session=latest))
    elif not enabled and existing is not None:
        db.delete(existing)
    db.commit()
    return enabled


def _has_active_run(db, user_id):
    return db.scalar(select(ForecastRun.id).where(
        ForecastRun.user_id == user_id, ForecastRun.status.in_(ACTIVE),
    ).limit(1)) is not None


def _busy():
    return ApiError(status_code=409, msg="已有一项走势分析在进行，请稍后再试")


def _queue(run):
    now = datetime.now(UTC)
    run.status = "queued"
    run.updated_at = run.next_delivery_at = now
    run.diagnosis = run.prediction = run.error = None
    run.models = {}


def _enqueue(db, user_id, snapshot, *, trigger):
    """Caller holds the per-user transaction lock. Return (run, needs_delivery)."""
    symbol = snapshot["symbol"]["code"]
    version = snapshot["data_version"] or f"empty-v{snapshot['feature_version']}"
    run = db.scalar(select(ForecastRun).where(
        ForecastRun.user_id == user_id, ForecastRun.symbol == symbol, ForecastRun.data_version == version,
    ))
    if run is not None and (run.status != "failed" or trigger != "manual"):
        return run, False
    ready = snapshot["status"] == "ready"
    if ready and _has_active_run(db, user_id):
        return None, False
    if run is None:
        run = ForecastRun(user_id=user_id, symbol=symbol, data_version=version, snapshot=snapshot,
                          trigger=trigger)
        db.add(run)
    if ready:
        _queue(run)
    else:
        run.status = "completed"
        run.prediction = forecast_analysis.insufficient(snapshot)
    db.flush()
    return run, run.status == "queued"


def _publish(run_id):
    from app.worker.tasks.forecast_tasks import run_forecast

    now = datetime.now(UTC)
    with get_session() as db:
        run = db.scalar(select(ForecastRun).where(
            ForecastRun.id == run_id, _delivery_due(now),
        ).options(load_only(ForecastRun.id, ForecastRun.next_delivery_at)).with_for_update(skip_locked=True))
        if run is None:
            return
        expires = now + DELIVERY_LIFETIME
        try:
            run_forecast.apply_async(args=(run_id,), retry=False, expires=expires)
        except Exception:
            run.next_delivery_at = datetime.now(UTC) + DELIVERY_RETRY
            logger.warning("Could not deliver forecast run %s", run_id, exc_info=True)
        else:
            # A successfully sent message remains the only delivery until it expires.
            run.next_delivery_at = expires
        db.commit()


def _delivery_due(now):
    return (ForecastRun.status == "queued") & or_(
        ForecastRun.next_delivery_at <= now, ForecastRun.next_delivery_at.is_(None),
    )


def _commit_run(db, run, deliver):
    response = as_response(run)
    db.commit()
    if deliver:
        _publish(response["id"])
    return response


def start_manual(db, user_id, symbol):
    snapshot = forecast_snapshot.build_snapshot(db, symbol)
    _lock_user(db, user_id)
    run, deliver = _enqueue(db, user_id, snapshot, trigger="manual")
    if run is None:
        raise _busy()
    return _commit_run(db, run, deliver)


def retry(db, user_id, run_id):
    _lock_user(db, user_id)
    run = db.scalar(select(ForecastRun).where(ForecastRun.id == run_id, ForecastRun.user_id == user_id)
                    .with_for_update())
    if run is None:
        raise ApiError(status_code=404, msg="未找到该走势分析记录")
    if run.status == "failed":
        if _has_active_run(db, user_id):
            raise _busy()
        _queue(run)
        return _commit_run(db, run, True)
    return _commit_run(db, run, False)


def _claim_due_tracking():
    now = datetime.now(UTC)
    with get_session() as db:
        due = db.scalar(select(ForecastTracking).join(User, User.id == ForecastTracking.user_id)
                        .where(User.is_deleted.is_(False), ForecastTracking.next_check_at <= now)
                        .order_by(ForecastTracking.next_check_at, ForecastTracking.user_id, ForecastTracking.symbol)
                        .limit(1).with_for_update(of=ForecastTracking, skip_locked=True))
        if due is None:
            return None
        due.next_check_at = now + TRACK_LEASE
        key = (due.user_id, due.symbol, due.last_session, due.next_check_at)
        db.commit()
        return key


def _track_one(user_id, symbol, previous, lease, now, snapshots):
    with get_session() as db:
        stock = forecast_snapshot.resolve_stock(db, symbol)
        latest = forecast_snapshot.latest_confirmed_session(db, stock.id, now)
        snapshot = None
        if latest is not None and (previous is None or latest > previous):
            if symbol not in snapshots:
                snapshots[symbol] = forecast_snapshot.build_snapshot(db, symbol, as_of=now)
            snapshot = snapshots[symbol]
        _lock_user(db, user_id)
        tracked = db.get(ForecastTracking, (user_id, symbol), with_for_update=True)
        if tracked is None or tracked.next_check_at != lease:
            return
        deliver = False
        session = date.fromisoformat(snapshot["latest_session"]) if snapshot and snapshot["latest_session"] else None
        if session is not None and (tracked.last_session is None or session > tracked.last_session):
            run, deliver = _enqueue(db, user_id, snapshot, trigger="auto")
            if run is None:
                return
            tracked.last_session = session
        tracked.next_check_at = datetime.now(UTC) + TRACK_INTERVAL
        db.commit()
        if deliver:
            _publish(run.id)


def sweep():
    now = datetime.now(UTC)
    deadline = monotonic() + TRACK_START_BUDGET
    with get_session() as db:
        db.execute(update(ForecastRun).where(
            ForecastRun.status.in_(("diagnosing", "predicting")), ForecastRun.updated_at < now - timedelta(minutes=10),
        ).values(status="failed", error="分析任务中断，请重试。", updated_at=now))
        ids = db.scalars(select(ForecastRun.id).where(_delivery_due(now))
                         .order_by(ForecastRun.next_delivery_at.nulls_first()).limit(SWEEP_LIMIT)).all()
        db.commit()
    for run_id in ids:
        _publish(run_id)
    snapshots = {}
    for _ in range(SWEEP_LIMIT):
        if monotonic() >= deadline:
            break
        claim = _claim_due_tracking()
        if claim is None:
            break
        user_id, symbol, previous, lease = claim
        try:
            _track_one(user_id, symbol, previous, lease, now, snapshots)
        except Exception:
            logger.warning("Forecast tracking check failed for %s", symbol, exc_info=True)


def _advance(run_id, lease, **fields):
    now = datetime.now(UTC)
    with get_session() as db:
        changed = db.execute(update(ForecastRun).where(
            ForecastRun.id == run_id, ForecastRun.updated_at == lease,
            ForecastRun.status.in_(("diagnosing", "predicting")),
        ).values(**fields, updated_at=now)).rowcount
        db.commit()
    return now if changed else None


def execute(run_id):
    lease = datetime.now(UTC)
    with get_session() as db:
        run = db.execute(update(ForecastRun).where(
            ForecastRun.id == run_id, ForecastRun.status == "queued",
        ).values(status="diagnosing", updated_at=lease, next_delivery_at=None).returning(
            ForecastRun.user_id, ForecastRun.snapshot,
        )).one_or_none()
        db.commit()
    if run is None:
        return

    async def analyze():
        nonlocal lease
        with get_session() as db:
            active = db.scalar(select(User.id).where(User.id == run.user_id, User.is_deleted.is_(False)))
            if active is None:
                _advance(run_id, lease, status="failed", error="账号已不可用。")
                return
            llm = build_llm_service_for_user(db, run.user_id)
        if not llm.available:
            _advance(run_id, lease, status="failed", error="AI 服务尚未配置，请在账号设置填写模型 API Key。")
            return
        diagnosis, model = await forecast_analysis.diagnose(llm, run.snapshot)
        models = {"diagnosis": model, "playbook_version": forecast_analysis.PLAYBOOK_VERSION}
        next_lease = _advance(run_id, lease, status="predicting", diagnosis=diagnosis, models=models)
        if next_lease is None:
            return
        lease = next_lease
        prediction, model = await forecast_analysis.predict(llm, run.snapshot, diagnosis)
        _advance(run_id, lease, status="completed", prediction=prediction, models={**models, "prediction": model})

    try:
        asyncio.run(analyze())
    except ValueError:
        _advance(run_id, lease, status="failed", error="AI 返回的格式或证据未通过校验，请重试。")
    except LLMError as exc:
        error = classify_llm_error(exc)
        _advance(run_id, lease, status="failed", error=str(error.get("message", "AI 服务暂不可用，请重试。"))[:240])
    except Exception:
        logger.warning("Forecast run %s failed", run_id, exc_info=True)
        _advance(run_id, lease, status="failed", error="走势分析未完成，请稍后重试。")
