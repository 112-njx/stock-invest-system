"""Manual online queries with a durable, process-shared cooldown and archives."""
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from stockdb_online_catalog import BY_ID, REPORTS, catalog
from stockdb_online_requests import OnlineError, parameters, invoke

NAMES = {key: entry['title'] for key, entry in BY_ID.items()}
LOCK = threading.Lock()


def normalize(value):
    if hasattr(value, 'to_frame') and not hasattr(value, 'columns'):
        value = value.to_frame()
    if hasattr(value, 'to_json'):
        # Preserve index keys (e.g. contract/date), including index/column name collisions.
        if hasattr(value, 'reset_index'):
            names = []
            for i, name in enumerate(value.index.names):
                candidate = str(name or f'index_{i}')
                while candidate in value.columns or candidate in names:
                    candidate = '原始_' + candidate
                names.append(candidate)
            value = value.rename_axis(names).reset_index()
        return json.loads(value.to_json(orient='records', date_format='iso', force_ascii=False))
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if hasattr(value, 'tolist'):
        return normalize(value.tolist())
    if isinstance(value, datetime):
        return value.isoformat()
    return value

def database():
    directory = Path(os.environ.get('STOCKDB_ONLINE_DIR', '/opt/stockdb/mydb/在线查询'))
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / '请求频率配置.sqlite', timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS quota (id INTEGER PRIMARY KEY, interval INTEGER, last REAL)')
    db.execute('INSERT OR IGNORE INTO quota VALUES (1,40,0)')
    db.execute("UPDATE quota SET interval=40 WHERE id=1 AND interval<40")
    db.commit()
    return directory, db

def policy(interval=None):
    _, db = database()
    try:
        if interval is not None:
            if type(interval) is not int or not 40 <= interval <= 86400:
                raise OnlineError('请求间隔应为 40 至 86400 秒')
            db.execute('UPDATE quota SET interval=? WHERE id=1', (interval,))
            db.commit()
        seconds, last = db.execute('SELECT interval,last FROM quota WHERE id=1').fetchone()
        return {'interval_seconds': seconds, 'retry_after': max(0, int(last + seconds - time.time() + 1))}
    finally:
        db.close()

def query(sdk_dir, payload):
    method, code, args = parameters(payload)
    if not LOCK.acquire(blocking=False):
        raise OnlineError('已有在线查询正在执行', 429, 40)
    try:
        directory, db = database()
        try:
            db.execute('BEGIN IMMEDIATE')
            interval, last = db.execute('SELECT interval,last FROM quota WHERE id=1').fetchone()
            now = time.time()
            if now - last < interval:
                raise OnlineError('在线请求冷却中', 429, int(last + interval - now + 1))
            db.execute('UPDATE quota SET last=? WHERE id=1', (now,))
            db.commit()
        finally:
            db.close()
        sys.path.insert(0, sdk_dir)
        import stock_sdk as sdk
        try:
            result = invoke(sdk, method, code, args)
        except Exception as exc:
            raise OnlineError('在线接口调用失败：' + str(exc)[:500], 502) from exc
        if isinstance(result, dict) and result.get('error'):
            raise OnlineError(str(result['error']), 502)
        if method == 'get_dominant_future' and isinstance(result, str) and not re.fullmatch(r'[A-Za-z]{1,8}[0-9]{3,6}(?:\.[A-Za-z]+)?', result):
            raise OnlineError(result[:500], 502)
        if result is None or (isinstance(result, str) and method != 'get_dominant_future'):
            raise OnlineError(str(result or '上游未返回有效结果'), 502)
        result = normalize(result)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        entry = BY_ID[method]
        title = NAMES[method]
        if method == 'get_fundamentals':
            title = REPORTS[args['report']]
        # Keep every path component readable and independent of user-supplied identifiers.
        def safe(value):
            return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(value))[:100] or '查询'
        relative = Path(safe(entry['group'])) / safe(title)
        folder = directory / relative
        folder.mkdir(parents=True, exist_ok=True)
        identity = code or args.get('underlying_symbol') or ('多标的' if method == 'get_factor_values' else '全市场')
        period = args.get('statDate', args.get('end_date', args.get('end_dt', args.get('date', '最新'))))
        filename = f"{safe(identity)}_{safe(period)}_{stamp}.json"
        warnings = []
        if code and isinstance(result, list):
            actual_codes = {str(row.get('code', row.get('sec_code', ''))).split('.')[0] for row in result if isinstance(row, dict)} - {''}
            if actual_codes and actual_codes != {code}:
                warnings.append('上游返回的股票与请求不一致，请以结果中的实际代码为准。')
        if isinstance(result, list) and args.get('start_date') and args.get('end_date'):
            dates = [str(row.get('date', row.get('day', '')))[:10].replace('-', '') for row in result if isinstance(row, dict)]
            if any(value and not args['start_date'].replace('-', '') <= value <= args['end_date'].replace('-', '') for value in dates):
                warnings.append('上游返回的日期超出请求范围，请核对实际数据日期。')
        record = {'method': method, 'parameters': payload, 'fetched_at': datetime.now().isoformat(), 'warnings': warnings, 'data': result}
        target = folder / filename
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False, default=str), encoding='utf-8')
        temp.replace(target)
        return {**record, 'saved_path': f'D:/Free_stockdb/stockdb/mydb/在线查询/{relative.as_posix()}/{filename}', **policy()}
    finally:
        LOCK.release()
