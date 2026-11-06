"""Shared on-disk update protocol and bounded full-result cache (stdlib only)."""
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4

ALGORITHM = 'industry-equalweight-2000-v1'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def data_version(control):
    state = read_json(Path(control) / 'version.json', {})
    if state.get('status') != 'ready' or not state.get('version'):
        raise RuntimeError('原始数据尚未验证就绪，请检查一键更新状态')
    return state['version']


def ensure_available(control):
    control = Path(control)
    if (control / 'maintenance.json').exists():
        raise RuntimeError('原始数据正在更新，本地源读取和同步暂时暂停')
    data_version(control)


class FullResultCache:
    """One complete result per industry/period/fq/algorithm/version; never annual slices."""
    def __init__(self, directory, max_bytes=128 * 1024 * 1024):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'industry.sqlite3'
        self.max_bytes = max_bytes
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, version TEXT NOT NULL, payload BLOB NOT NULL, touched REAL NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA cache_size=-4096')
            db.execute('PRAGMA mmap_size=0')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def key(code, frequency, version):
        return json.dumps([code, frequency, 'qfq', ALGORITHM, version], separators=(',', ':'))

    def get(self, code, frequency, version):
        key = self.key(code, frequency, version)
        with self.connect() as db:
            row = db.execute('SELECT payload FROM results WHERE key=?', (key,)).fetchone()
            if row:
                db.execute('UPDATE results SET touched=? WHERE key=?', (time.time(), key))
                return json.loads(row[0])
        return None

    def put(self, code, frequency, version, rows):
        if not isinstance(rows, list) or not rows:
            return
        if any(not isinstance(r, dict) or not all(k in r for k in ('date', 'open', 'high', 'low', 'close')) for r in rows):
            raise ValueError('invalid full industry result')
        dates = [r['date'] for r in rows]
        if dates != sorted(set(dates)):
            raise ValueError('invalid industry chronology')
        encoded = json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        if len(encoded) > self.max_bytes:
            return
        with self.connect() as db:
            db.execute('DELETE FROM results WHERE version<>?', (version,))
            # Different end cutoffs may yield partial week/month bars; retain only
            # one complete cutoff snapshot per industry/period to avoid duplicates.
            for (existing,) in db.execute('SELECT key FROM results').fetchall():
                parts = json.loads(existing)
                if parts[0].split('@')[0] == code.split('@')[0] and parts[1] == frequency:
                    db.execute('DELETE FROM results WHERE key=?', (existing,))
            db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?)',
                       (self.key(code, frequency, version), version, encoded, time.time()))
            while db.execute('SELECT COALESCE(SUM(length(payload)),0) FROM results').fetchone()[0] > self.max_bytes:
                db.execute('DELETE FROM results WHERE key=(SELECT key FROM results ORDER BY touched LIMIT 1)')
        # SQLite reuses freed pages; payload capacity bounds future growth.


def manifest_fingerprint(root, verify=False, progress=None):
    """Cover all downloaded manifests, including historical corrections on the same date."""
    root = Path(root)
    digest = hashlib.sha256()
    manifests = sorted(root.glob('data*/.sync_manifest.json'))
    if not manifests:
        raise RuntimeError('未找到下载清单 .sync_manifest.json')
    count = 0
    for manifest in manifests:
        raw = manifest.read_bytes()
        digest.update(manifest.parent.name.encode() + raw)
        if not verify:
            # Once LevelDB has opened a downloaded snapshot it may rotate WALs
            # named in the download manifest. Baseline the current files instead.
            for path in sorted(manifest.parent.iterdir()):
                if path.is_file() and (path.suffix in {'.ldb', '.sst'} or path.name == 'CURRENT' or path.name.startswith('MANIFEST-')):
                    stat = path.stat()
                    digest.update(f'{path.name}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
            continue
        files = json.loads(raw)['files']
        for item in files:
            path = (manifest.parent / item['path']).resolve()
            if not path.is_relative_to(manifest.parent.resolve()):
                raise ValueError('invalid manifest path')
            stat = path.stat()
            if stat.st_size != item['size']:
                raise RuntimeError(f'清单文件大小不匹配：{path.name}')
            digest.update(f'{item["path"]}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
            if verify:
                expected = item.get('sha256')
                if not expected:
                    raise RuntimeError(f'清单缺少 SHA-256：{path.name}')
                with path.open('rb') as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual.lower() != expected.lower():
                    raise RuntimeError(f'清单 SHA-256 不匹配：{path.name}')
            count += 1
            if progress:
                progress(count)
    return digest.hexdigest()
