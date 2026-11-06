"""Admin-only fixed command queue to the Windows update helper, not a shell API."""
import os
import time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, text
from fastapi import HTTPException
from app.models.ops import SyncTask
from app.utils.db import get_session
from .stockdb_files import read_json, write_json


def directory():
    return Path(os.environ.get('STOCKDB_CONTROL_DIR', '/app/data/stockdb-control'))


def status():
    root = directory()
    helper = read_json(root / 'heartbeat.json', {})
    state = read_json(root / 'status.json', {'status': 'idle', 'phase': 'idle', 'progress': 0,
                                             'message': '尚未执行原始数据更新', 'error': None, 'task_id': None})
    return {**state, 'helper_online': time.time() - helper.get('time', 0) < 30,
            'maintenance': (root / 'maintenance.json').exists(),
            'can_retry': state.get('status') == 'failed' and not (root / 'updater-process.json').exists(),
            'data_version': read_json(root / 'version.json', {}).get('version')}


def request_update():
    from .local_market_sync import LOCK_KEY, TASK_TYPE
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    if not status()['helper_online']:
        raise HTTPException(503, '本机更新助手未连接，请先运行 deploy/start_stockdb_update_agent.ps1')
    db = get_session()
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK_KEY})
        job = db.scalar(select(SyncTask).where(SyncTask.task_type == TASK_TYPE))
        if job and job.status in {'queued', 'running'}:
            raise HTTPException(409, '行情同步正在执行，请完成后再更新原始文件')
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
                       'progress': 0, 'message': '等待本机助手更新原始文件；不会自动导入项目数据库', 'error': None})
            write_json(root / 'request.json', {'task_id': task_id, 'operation': 'update', 'created_at': time.time()})
        except Exception:
            (root / 'maintenance.json').unlink(missing_ok=True)
            raise
        db.commit()
        return status()
    finally:
        db.close()
