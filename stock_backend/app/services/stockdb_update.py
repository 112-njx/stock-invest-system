"""Admin-only fixed command queue to the Linux container controller, not a shell API."""
import os
import time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from fastapi import HTTPException
from app.utils.db import get_session
from .stockdb_files import read_json, write_json


def directory():
    return Path(os.environ.get('STOCKDB_CONTROL_DIR', '/app/data/stockdb-control'))


def ready_version() -> str | None:
    root = directory()
    if (root / 'maintenance.json').exists():
        return None
    manifest = read_json(root / 'version.json', {})
    return manifest.get('version') if manifest.get('status') == 'ready' else None


def status():
    root = directory()
    helper = read_json(root / 'heartbeat.json', {})
    state = read_json(root / 'status.json', {'status': 'idle', 'phase': 'idle', 'progress': 0,
                                             'message': '尚未执行原始数据更新', 'error': None, 'task_id': None})
    return {**state, 'helper_online': helper.get('kind') == 'linux-container' and time.time() - helper.get('time', 0) < 30,
            'maintenance': (root / 'maintenance.json').exists(),
            'can_retry': state.get('status') == 'failed' and not (root / 'updater-process.json').exists(),
            'data_version': read_json(root / 'version.json', {}).get('version')}


def request_update(*, scheduled_day=None):
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    if not status()['helper_online']:
        raise HTTPException(503, '容器更新控制器未连接，请检查 stockdb-local 容器')
    db = get_session()
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 6100000001})
        schedule_file = root / 'scheduled-update.json'
        if scheduled_day and read_json(schedule_file, {}).get('day') == scheduled_day:
            raise HTTPException(409, '已提交今日自动更新')
        task_id = str(uuid4())
        previous = status()
        if previous.get('status') in {'queued', 'running'}:
            raise HTTPException(409, '已有原始数据更新任务正在执行')
        if previous['can_retry']:
            (root / 'maintenance.json').unlink(missing_ok=True)
        # Exclusive creation coordinates all API processes with the host helper.
        try:
            with (root / 'maintenance.json').open('x', encoding='utf-8') as stream:
                stream.write('{}')
        except FileExistsError:
            raise HTTPException(409, '已有更新或未恢复的维护任务，请先检查更新状态')
        try:
            write_json(root / 'status.json', {'task_id': task_id, 'status': 'queued', 'phase': 'queued',
                       'progress': 0, 'message': '等待容器控制器更新原始文件；不会自动导入项目数据库', 'error': None})
            if scheduled_day:
                write_json(schedule_file, {'day': scheduled_day, 'task_id': task_id})
            write_json(root / 'request.json', {'task_id': task_id, 'operation': 'update', 'created_at': time.time()})
        except Exception as exc:
            # No queued status may survive without a job for the helper to claim.
            # Remove the job before publishing a retryable terminal state.
            (root / 'request.json').unlink(missing_ok=True)
            if scheduled_day:
                schedule_file.unlink(missing_ok=True)
            try:
                write_json(root / 'status.json', {'task_id': task_id, 'status': 'failed', 'phase': 'failed',
                           'progress': 0, 'message': '更新请求提交失败，尚未执行更新，请重试', 'error': str(exc)})
            except OSError:
                # A full/unwritable disk can also prevent writing the failure state.
                # Falling back to idle is preferable to an unrecoverable queued job.
                (root / 'status.json').unlink(missing_ok=True)
            (root / 'maintenance.json').unlink(missing_ok=True)
            raise
        db.commit()
        return status()
    finally:
        db.close()


def dispatch_version_change():
    """Publish dependent work once per verified StockDB file version."""
    version = ready_version()
    if not version:
        return
    from app.utils.redis_client import get_redis_client
    from app.worker.tasks.forecast_tasks import sweep_forecasts
    from app.worker.tasks.sync_tasks import refresh_stockdb_catalog

    redis = get_redis_client()
    key = 'stockdb:dispatched-file-version'
    if redis.get(key) == version:
        return
    lock = redis.lock(key + ':lock', timeout=60, blocking_timeout=0)
    if not lock.acquire():
        return
    try:
        if redis.get(key) != version:
            refresh_stockdb_catalog.delay()
            sweep_forecasts.delay()
            redis.set(key, version)
    finally:
        lock.release()


def events(task_id, after_seq=0, before_seq=None, limit=200):
    import sqlite3
    from uuid import UUID
    try:
        UUID(task_id)
    except ValueError:
        raise HTTPException(400, '无效的更新任务编号')
    path = directory()/'update-events.sqlite3'
    if not path.exists():
        return {'events':[], 'files':[], 'has_more':False}
    db = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        if before_seq is not None:
            rows = db.execute('SELECT * FROM events WHERE task=? AND seq<? ORDER BY seq DESC LIMIT ?', (task_id,before_seq,limit+1)).fetchall()
            result = list(reversed(rows[:limit]))
        else:
            rows = db.execute('SELECT * FROM events WHERE task=? AND seq>? ORDER BY seq LIMIT ?', (task_id,after_seq,limit+1)).fetchall()
            result = rows[:limit]
        files = db.execute('SELECT file,status,retries FROM files WHERE task=? ORDER BY file LIMIT 500', (task_id,)).fetchall()
        return {'events':[dict(r) for r in result], 'files':[dict(r) for r in files], 'has_more':len(rows)>limit}
    finally:
        db.close()
