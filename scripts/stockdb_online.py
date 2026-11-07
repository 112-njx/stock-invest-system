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

NAMES = {'get_last_tick': '实时逐笔', 'get_ticks': '历史逐笔', 'get_fundamentals': '财务报表', 'get_billboard_list': '龙虎榜', 'get_locked_shares': '限售解禁', 'get_money_flow': '资金流向', 'get_mtss': '融资融券'}
LOCK = threading.Lock()

def normalize(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value

class OnlineError(Exception):
    def __init__(self, message, status=400, retry_after=0):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after

def database():
    directory = Path(os.environ.get('STOCKDB_ONLINE_DIR', '/opt/stockdb/mydb/在线查询'))
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / '请求频率配置.sqlite', timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS quota (id INTEGER PRIMARY KEY, interval INTEGER, last REAL)')
    db.execute('INSERT OR IGNORE INTO quota VALUES (1,30,0)')
    db.commit()
    return directory, db

def policy(interval=None):
    _, db = database()
    try:
        if interval is not None:
            if type(interval) is not int or not 30 <= interval <= 86400:
                raise OnlineError('请求间隔应为 30 至 86400 秒')
            db.execute('UPDATE quota SET interval=? WHERE id=1', (interval,))
            db.commit()
        seconds, last = db.execute('SELECT interval,last FROM quota WHERE id=1').fetchone()
        return {'interval_seconds': seconds, 'retry_after': max(0, int(last + seconds - time.time() + 1))}
    finally:
        db.close()

def parameters(payload):
    method = payload.get('method')
    if method not in NAMES:
        raise OnlineError('不支持的数据类型')
    code = payload.get('code', '').strip()
    if code and not re.fullmatch(r'[0-9]{6}', code):
        raise OnlineError('股票代码应为六位数字')
    if not code and method in ('get_last_tick', 'get_ticks', 'get_money_flow', 'get_mtss', 'get_locked_shares'):
        raise OnlineError('此接口需要股票代码')
    count = payload.get('count', 20)
    if type(count) is not int or not 1 <= count <= 1000:
        raise OnlineError('条数应为 1 至 1000')
    args = {}
    if method in ('get_last_tick', 'get_ticks'):
        args = {'security': code, 'count': count}
        if method == 'get_ticks':
            value = payload.get('end_dt', '')
            try:
                datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                raise OnlineError('请选择历史逐笔截止时间')
            args['end_dt'] = value
    elif method == 'get_fundamentals':
        if payload.get('report') not in ('income', 'balance', 'cash_flow'):
            raise OnlineError('请选择三大报表')
        if not re.fullmatch(r'20[0-9]{2}q[1-4]', payload.get('quarter', '')):
            raise OnlineError('报告期格式为 2024q4')
    else:
        for key in ('start_date', 'end_date'):
            value = payload.get(key, '')
            try:
                datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                raise OnlineError('请选择开始和结束日期')
            args[key] = value
        if args['start_date'] > args['end_date']:
            raise OnlineError('开始日期不能晚于结束日期')
        args['security_list' if method in ('get_mtss', 'get_money_flow') else 'stock_list'] = [code] if code else None
    return method, code, args

def query(sdk_dir, payload):
    method, code, args = parameters(payload)
    if not LOCK.acquire(blocking=False):
        raise OnlineError('已有在线查询正在执行', 429, 30)
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
        if method == 'get_fundamentals':
            table = getattr(sdk, payload['report'])
            q = sdk.query(table)
            if code:
                q = q.filter(table.code == code + ('.XSHG' if code.startswith('6') else '.XSHE'))
            result = sdk.get_fundamentals(q, statDate=payload['quarter'])
        else:
            result = getattr(sdk, method)(**args)
        if isinstance(result, dict) and result.get('error'):
            raise OnlineError(str(result['error']), 502)
        if result is None or isinstance(result, str):
            raise OnlineError(str(result or '上游未返回有效结果'), 502)
        if hasattr(result, 'to_json'):
            result = json.loads(result.reset_index().to_json(orient='records', date_format='iso', force_ascii=False))
        result = normalize(result)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        folder = directory / NAMES[method]
        folder.mkdir(exist_ok=True)
        report_names = {'income': '利润表', 'balance': '资产负债表', 'cash_flow': '现金流量表'}
        period = (report_names[payload['report']] + '_' + payload['quarter']) if method == 'get_fundamentals' else args.get('end_date', args.get('end_dt', '最新')).replace(':', '').replace(' ', '_')
        filename = f"{code or '全市场'}_{period}_{stamp}.json"
        warnings = []
        if code and isinstance(result, list):
            actual_codes = {str(row.get('code', row.get('sec_code', ''))).split('.')[0] for row in result if isinstance(row, dict)} - {''}
            if actual_codes and actual_codes != {code}:
                warnings.append('上游返回的股票与请求不一致，请以结果中的实际代码为准。')
        if isinstance(result, list) and args.get('start_date'):
            dates = [str(row.get('date', row.get('day', '')))[:10].replace('-', '') for row in result if isinstance(row, dict)]
            if any(value and not args['start_date'].replace('-', '') <= value <= args['end_date'].replace('-', '') for value in dates):
                warnings.append('上游返回的日期超出请求范围，请核对实际数据日期。')
        record = {'method': method, 'parameters': payload, 'fetched_at': datetime.now().isoformat(), 'warnings': warnings, 'data': result}
        target = folder / filename
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False, default=str), encoding='utf-8')
        temp.replace(target)
        return {**record, 'saved_path': f'D:/Free_stockdb/stockdb/mydb/在线查询/{NAMES[method]}/{filename}', **policy()}
    finally:
        LOCK.release()
