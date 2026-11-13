"""Replay the forecast on chronological prefixes and score separate future labels."""

import asyncio
import hashlib
import json
import logging
import math
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update

from app.core.exceptions import ApiError
from app.data_providers.base import DAILY_SESSION_CLOSE, DAILY_SESSION_TZ
from app.data_providers.stockdb import StockDBProvider
from app.models.forecast import ForecastReplay, ForecastRun
from app.models.user import User
from app.services import forecast_analysis, forecast_snapshot, sdk_indicators
from app.services.forecast_runs import _lock_user
from app.services.indicator_registry import FORECAST_FEATURES, FORECAST_FEATURE_VERSION
from app.services.llm.user_key import build_llm_service_for_user
from app.utils.db import get_session

logger = logging.getLogger(__name__)
HORIZON = forecast_analysis.REGIME_HORIZON
WARMUP_DAYS = 550
RULE_VERSION = 1
PRICE_FIELDS = ("open", "high", "low", "close")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _adjust(rows, timeline):
    """Use effective factors through the last row of this particular window."""
    days = [day for day, _ in timeline]
    def factor_at(day):
        index = bisect_right(days, day)
        return timeline[index - 1][1] if index else 1.0
    base = factor_at(int(rows[-1]["ts"].replace("-", "")))
    result = []
    for row in rows:
        ratio = factor_at(int(row["ts"].replace("-", ""))) / base
        result.append({
            **row, **{key: round(row[key] * ratio, 2) for key in PRICE_FIELDS},
        } if abs(ratio - 1) >= 1e-6 else row.copy())
    return result


def _read_market(symbol, end):
    provider = StockDBProvider()
    now = datetime.now(UTC)
    available = provider.daily_confirmation_cutoff(now)
    if available is None:
        raise ValueError("StockDB has no confirmed file version")
    local = available.astimezone(DAILY_SESSION_TZ)
    closed = local.date() - timedelta(days=local.time() < DAILY_SESSION_CLOSE)
    reference = end or closed
    through = min(closed, reference + timedelta(days=45))
    timeline = provider.adjustment_timeline(symbol)
    if any(not math.isfinite(factor) or factor <= 0 for _, factor in timeline):
        raise ValueError("invalid adjustment factor")
    raw = {}
    start = reference - timedelta(days=WARMUP_DAYS)
    for bar in provider.raw_daily_history(symbol, start, through):
        day = datetime.strptime(str(bar["date"]), "%Y%m%d").date()
        if bar["code"] != symbol or not start <= day <= through:
            raise ValueError("unexpected stock or session")
        row = {key: float(bar[key]) for key in PRICE_FIELDS}
        volume = int(bar.get("volume") or 0)
        amount = float(bar.get("amount") or 0)
        if day.weekday() >= 5 or (volume == 0 and amount == 0):
            continue
        if (day in raw or not all(math.isfinite(v) and v > 0 for v in row.values())
                or not math.isfinite(amount) or min(volume, amount) < 0
                or not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]):
            raise ValueError("invalid daily bar")
        raw[day] = dict(row, ts=day.isoformat(), volume=volume // 100, amount=amount)
    if provider.daily_confirmation_cutoff(now) != available:
        raise ValueError("StockDB changed during replay preparation")
    rows = [raw[day] for day in sorted(raw)]
    return rows, timeline, _digest([rows, [(day, f) for day, f in timeline if day <= int(through.strftime("%Y%m%d"))]])


def _direction(bar):
    return "up" if bar["close"] > bar["open"] else "down" if bar["close"] < bar["open"] else "flat"


def _regime(history, future):
    """Classify a five-bar path with levels and volatility fixed at its origin."""
    if len(history) < 20 or len(future) != HORIZON:
        return None
    recent = history[-20:]
    atr = sum(max(bar["high"], prev["close"]) - min(bar["low"], prev["close"])
              for prev, bar in zip(recent[-15:-1], recent[-14:])) / 14
    closes = [history[-1]["close"], *(bar["close"] for bar in future)]
    high = max(bar["high"] for bar in recent)
    low = min(bar["low"] for bar in recent)
    if (closes[-2] > high and closes[-1] > high + 0.5 * atr
            or closes[-2] < low and closes[-1] < low - 0.5 * atr):
        return "breakout"
    change = abs(closes[-1] - closes[0])
    path = sum(abs(right - left) for left, right in zip(closes, closes[1:]))
    efficiency = change / path if path else 0
    if change and change >= atr and efficiency >= 0.8:
        return "trend"
    if change and change >= 0.75 * atr and efficiency >= 0.45:
        return "tight_channel" if efficiency >= 0.65 else "broad_channel"
    return "range"


def _case(rows, timeline, index):
    history = _adjust(rows[:index + 1], timeline)
    follow = rows[index + 1:index + 1 + HORIZON]
    result = {
        "session": history[-1]["ts"],
        "next_session": follow[0]["ts"] if follow else None,
        "regime_through": follow[-1]["ts"] if len(follow) == HORIZON else None,
        "actual_direction": _direction(follow[0]) if follow else None,
        "actual_regime": None,
        "last_candle": _direction(rows[index]),
        "always_up": "up",
        "previous_regime": _regime(history[:-HORIZON], history[-HORIZON:]),
    }
    if len(follow) == HORIZON:
        # Labels can use factors through the observation window. Inputs never do.
        label_rows = _adjust(rows[max(0, index - 19):index + 1 + HORIZON], timeline)
        result["actual_regime"] = _regime(label_rows[:-HORIZON], label_rows[-HORIZON:])
    return history, result


def _scores(cases):
    output = {}
    for label, methods in (
        ("actual_direction", ("direction", "last_candle", "always_up")),
        ("actual_regime", ("regime", "previous_regime")),
    ):
        labelled = [case for case in cases if case[label] is not None]
        for method in methods:
            covered = [case for case in labelled if case.get(method) not in (None, "undetermined")]
            hits = sum(case[method] == case[label] for case in covered)
            output[method] = {"labelled": len(labelled), "covered": len(covered), "hits": hits}
    return output


def _archived_inputs(db, user_id, symbol, sessions):
    saved = {}
    cutoff = ForecastRun.snapshot["latest_session"].astext
    runs = db.execute(select(ForecastRun.snapshot, ForecastRun.created_at).where(
        ForecastRun.user_id == user_id, ForecastRun.symbol == symbol, cutoff.in_(sessions),
    ).order_by(ForecastRun.id))
    for snapshot, created_at in runs:
        session = snapshot["latest_session"]
        as_of = datetime.fromisoformat(snapshot["as_of"]).astimezone(DAILY_SESSION_TZ)
        if (snapshot["status"] == "ready" and as_of.date().isoformat() == session
                and as_of.time() >= DAILY_SESSION_CLOSE
                and created_at.astimezone(DAILY_SESSION_TZ).date() == as_of.date()
                and snapshot["rows"] and snapshot["rows"][-1]["ts"] == session
                and all(row["ts"] <= session for row in snapshot["rows"])):
            saved.setdefault(session, snapshot)
    return saved


def _reconstructed(history):
    rows = sdk_indicators.calculate(history, [FORECAST_FEATURES], None, period="1d")
    return {
        "latest_session": history[-1]["ts"], "rows": rows[-forecast_snapshot.RESULT_WINDOW:],
        "data_version": _digest(history), "feature_version": FORECAST_FEATURE_VERSION,
    }


def _response(row):
    return {key: getattr(row, key) for key in ("id", "status", "options", "report", "error")}


def latest(db, user_id, symbol):
    row = db.scalar(select(ForecastReplay).where(
        ForecastReplay.user_id == user_id, ForecastReplay.symbol == symbol,
    ).order_by(ForecastReplay.id.desc()).limit(1))
    return _response(row) if row else None


def start(db, user_id, symbol, options):
    forecast_snapshot.resolve_stock(db, symbol)
    _lock_user(db, user_id)
    if db.scalar(select(ForecastReplay.id).where(
        ForecastReplay.user_id == user_id, ForecastReplay.status.in_(("queued", "running")),
    )) is not None:
        raise ApiError(status_code=409, msg="已有历史回放在进行")
    row = ForecastReplay(user_id=user_id, symbol=symbol, options=options, status="queued")
    db.add(row)
    db.commit()
    return _response(row)


def _save(job_id, report, status="running", error=None):
    with get_session() as db:
        changed = db.execute(update(ForecastReplay).where(
            ForecastReplay.id == job_id, ForecastReplay.status == "running",
        ).values(status=status, report=report, error=error, updated_at=datetime.now(UTC))).rowcount
        db.commit()
    return bool(changed)


async def _predict_case(llm, snapshot):
    diagnosis, diagnostic_model = await forecast_analysis.diagnose(llm, snapshot)
    prediction, predictive_model = await forecast_analysis.predict(llm, snapshot, diagnosis)
    return {
        "direction": prediction["next_candle"]["direction"], "regime": prediction["next_regime"]["regime"],
        "models": {"diagnosis": diagnostic_model, "prediction": predictive_model,
                   "playbook_version": forecast_analysis.PLAYBOOK_VERSION},
    }


def _evaluate(job, report):
    end = date.fromisoformat(job.options["end"]) if job.options["end"] else None
    rows, timeline, version = _read_market(job.symbol, end)
    stop = sum(row["ts"] <= end.isoformat() for row in rows) if end else max(0, len(rows) - HORIZON)
    indexes = range(max(0, stop - job.options["samples"]), stop)
    report.update(total=len(indexes), market_version=version)
    with get_session() as db:
        llm = build_llm_service_for_user(db, job.user_id)
        archives = _archived_inputs(db, job.user_id, job.symbol, [rows[i]["ts"] for i in indexes]) \
            if job.options["mode"] == "archived" else None
    if not llm.available and (archives if archives is not None else any(
        index + 1 >= forecast_snapshot.MIN_BARS and index + 1 < len(rows) for index in indexes
    )):
        raise ApiError(status_code=409, msg="AI 服务尚未配置，请先设置模型 API Key")
    for index in indexes:
        history, case = _case(rows, timeline, index)
        if case["actual_direction"] is None:
            case["status"] = "unlabelled"
        elif archives is not None and case["session"] not in archives:
            case["status"] = "missing_archive"
        elif archives is None and len(history) < forecast_snapshot.MIN_BARS:
            case["status"] = "insufficient"
        else:
            try:
                snapshot = archives[case["session"]] if archives is not None else _reconstructed(history)
                if archives is not None:
                    known = snapshot["rows"]
                    case["last_candle"] = _direction(known[-1])
                    case["previous_regime"] = _regime(known[:-HORIZON], known[-HORIZON:])
                case.update(data_version=snapshot["data_version"], feature_version=snapshot["feature_version"])
                case.update(asyncio.run(_predict_case(llm, snapshot)), status="evaluated")
            except Exception:
                logger.warning("Replay %s failed for %s", job.id, case["session"], exc_info=True)
                case["status"] = "failed"
        report["cases"].append(case)
        report["scores"] = _scores(report["cases"])
        if not _save(job.id, report):
            return
    _save(job.id, report, "completed")


def work_once():
    now = datetime.now(UTC)
    with get_session() as db:
        db.execute(update(ForecastReplay).where(
            ForecastReplay.status == "running", ForecastReplay.updated_at < now - timedelta(minutes=55),
        ).values(status="failed", error="回放任务中断，可重新提交", updated_at=now))
        job = db.scalar(select(ForecastReplay).join(User).where(
            ForecastReplay.status == "queued", User.is_deleted.is_(False),
        ).order_by(ForecastReplay.id).limit(1).with_for_update(of=ForecastReplay, skip_locked=True))
        if job is None:
            db.commit()
            return
        job.status, job.updated_at = "running", now
        db.commit()
    report = {"cases": [], "scores": _scores([]), "total": 0, "rule_version": RULE_VERSION, "horizon": HORIZON}
    try:
        _evaluate(job, report)
    except ApiError as exc:
        _save(job.id, report, "failed", exc.msg)
    except Exception:
        logger.exception("Forecast replay %s failed", job.id)
        _save(job.id, report, "failed", "无法读取或处理回放行情，请检查本地数据源后重试")
