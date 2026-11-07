"""Linux update controller. Data stays in the existing bind mounts."""
import json
import os
import re
import select
import signal
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from stockdb_files import read_json, write_json, manifest_fingerprint


class Events:
    def __init__(self, root):
        self.path = Path(root) / 'update-events.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, time REAL, phase TEXT, level TEXT, file TEXT, message TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS events_task_seq ON events(task,seq)')
            db.execute('CREATE TABLE IF NOT EXISTS files(task TEXT, file TEXT, status TEXT, retries INTEGER DEFAULT 0, PRIMARY KEY(task,file))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, task, phase, message, level='info', file=None, status=None, retry=False):
        with self.connect() as db:
            db.execute('INSERT INTO events(task,time,phase,level,file,message) VALUES(?,?,?,?,?,?)',
                       (task, time.time(), phase, level, file, message))
            if file:
                db.execute('INSERT INTO files(task,file,status,retries) VALUES(?,?,?,?) ON CONFLICT(task,file) DO UPDATE SET status=excluded.status, retries=MAX(files.retries,excluded.retries)',
                           (task, file, status or 'downloading', int(retry)))


class Controller:
    def __init__(self, root, data, start, stop, probe):
        self.root, self.data = Path(root), Path(data)
        self.root.mkdir(parents=True, exist_ok=True)
        self.events = Events(self.root)
        self.start, self.stop, self.probe = start, stop, probe
        self.task = None
        self.completed = False
        self.details = {}

    def report(self, phase, progress, message, status='running', error=None):
        self.events.append(self.task, phase, message, 'error' if error else 'info')
        write_json(self.root/'status.json', dict(task_id=self.task, status=status, phase=phase,
                   progress=progress, message=message, error=error, details=self.details,
                   updated_at=time.time()))

    def line(self, raw):
        message = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', raw).strip()
        if not message:
            return
        # Preserve updater events, but do not expose source URLs, tokens or device IDs.
        message = re.sub(r'https?://\S+', '[数据源地址]', message)
        message = re.sub(r'(?i)(ID:\s*)\S+', r'\1[已隐藏]', message)
        phase, level, filename, state, retry = 'downloading', 'info', None, None, False
        match = re.search(r'([\w./-]+\.(?:ldb|sst|log)|MANIFEST-\d+|\bCURRENT\b)', message)
        if match:
            filename = re.sub(r'^range(?=\d)', '', match[1])
            attempt = re.search(r'(?:续传|retry|重试)\s*(\d+)', message, re.I)
            retry = int(attempt[1]) if attempt else 0
            state = 'retrying' if re.search(r'续传|retry|重试', message, re.I) else 'done' if re.search(r'\bok\b|成功|完成', message, re.I) else 'downloading'
            if re.search(r'合并|merged', message, re.I):
                phase = 'merging'
                if state != 'done':
                    state = 'merging'
            if re.search(r'删除|\bdelet(?:e|ed|ing)\b', message, re.I):
                state = 'deleted' if re.search(r'完成|成功|deleted|\bok\b', message, re.I) else 'deleting'
            if re.search(r'跳过|复用|\bskip', message, re.I):
                state = 'reused'
        if re.search(r'error|失败|错误', message, re.I):
            level = 'error'
            if filename:
                state = 'failed'
        counts = re.search(r'待(下载|删除)资源数[:：]\s*(\d+)', message)
        if counts:
            self.details['download_files' if counts[1] == '下载' else 'delete_files'] = int(counts[2])
        # This is the updater's aggregate byte progress, not the out-of-order file index.
        transfer = re.search(r'([\d.]+\s*[KMGT]?B?)\s*/\s*([\d.]+\s*[KMGT]?B?)\s*\(([\d.]+)%\)\s*(.*)', message, re.I)
        if transfer:
            self.details.update(downloaded=transfer[1], total=transfer[2], download_percent=float(transfer[3]), speed=transfer[4])
        if re.search(r'Success.*(?:100%|完成)|同步已\s*100%\s*完成', message, re.I):
            self.completed = True
        self.events.append(self.task, phase, message, level, filename, state, retry)
        state_json = read_json(self.root/'status.json', {})
        if transfer:
            state_json['progress'] = min(70, 15 + int(float(transfer[3]) * .55))
        state_json.update(details=self.details, updated_at=time.time())
        write_json(self.root/'status.json', state_json)

    def run_updater(self):
        import pty
        master, slave = pty.openpty()
        process = subprocess.Popen([str(self.data/'数据更新')], cwd=self.data,
                                   stdin=subprocess.DEVNULL, stdout=slave, stderr=slave,
                                   start_new_session=True)
        os.close(slave)
        pending = b''
        deadline = time.monotonic() + 4*3600
        try:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError('原始数据更新超过 4 小时')
                readable, _, _ = select.select([master], [], [], .5)
                if readable:
                    try:
                        block = os.read(master, 65536)
                    except OSError:
                        block = b''
                    if not block:
                        break
                    pending += block
                    lines = re.split(b'[\r\n]', pending)
                    pending = lines.pop()
                    for line in lines:
                        self.line(line.decode('utf-8', errors='replace'))
                    if len(pending) > 65536:
                        self.line(pending.decode('utf-8', errors='replace')); pending = b''
                elif process.poll() is not None:
                    break
            if pending:
                self.line(pending.decode('utf-8', errors='replace'))
            code = process.wait(timeout=10)
            if code or not self.completed:
                raise RuntimeError(f'更新器未确认同步完成（退出码 {code}），请查看运行日志')
        finally:
            os.close(master)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    def recover(self):
        state = read_json(self.root/'status.json', {})
        orphan = (self.root/'maintenance.json').exists() and state.get('status') != 'failed' and not (self.root/'request.json').exists()
        if state.get('status') == 'running' or orphan:
            self.task = state.get('task_id')
            (self.root/'request.json').unlink(missing_ok=True)
            (self.root/'active-request.json').unlink(missing_ok=True)
            write_json(self.root/'version.json', {'status':'failed', 'version':None})
            self.report('failed', 0, '容器在更新过程中中断，本地源保持维护状态，请检查日志后重试', 'failed', 'interrupted container update')

    def recover_orphan(self, now=None):
        """Called only when no update worker is alive; allow an API submission grace period."""
        marker = self.root/'maintenance.json'
        if not marker.exists() or (self.root/'request.json').exists():
            return False
        if (time.time() if now is None else now) - marker.stat().st_mtime < 30:
            return False
        state = read_json(self.root/'status.json', {})
        if state.get('status') == 'failed':
            return False
        self.stop()
        self.task = state.get('task_id')
        (self.root/'active-request.json').unlink(missing_ok=True)
        write_json(self.root/'version.json', {'status':'failed', 'version':None})
        self.report('failed', 0, '更新提交或执行已中断，本地源保持维护状态，可重新提交更新',
                    'failed', 'orphaned update without an active worker')
        return True

    def execute(self, job):
        self.task, self.completed, self.details = job['task_id'], False, {}
        if job.get('operation') != 'update':
            raise ValueError('unsupported update operation')
        if (self.root/'request.json').exists():
            os.replace(self.root/'request.json', self.root/'active-request.json')
        (self.root/'maintenance.json').touch(exist_ok=True)
        try:
            self.report('checking', 2, '检查 Linux 更新器及数据源配置')
            if not os.access(self.data/'数据更新', os.X_OK) or not (self.data/'sync_url.txt').is_file():
                raise RuntimeError('容器缺少可执行更新器或 sync_url.txt')
            self.report('stopping', 5, '暂停本地读取，停止 RD 和 SDK 子进程')
            self.stop()
            write_json(self.root/'version.json', {'status':'updating', 'version':None})
            self.report('downloading', 15, 'Linux 更新器运行中，原始文件直接写入现有 D 盘挂载目录')
            self.run_updater()
            self.report('verifying', 75, '下载结束，开始校验原始文件')
            last = [0.0]
            def progress(count):
                if time.monotonic()-last[0] >= 1:
                    self.details['verified_files'] = count
                    self.report('verifying', 80, f'已校验 {count} 个文件')
                    last[0] = time.monotonic()
            fingerprint = manifest_fingerprint(self.data, verify=True, progress=progress)
            write_json(self.root/'version.json', {'status':'ready','version':uuid4().hex,'fingerprint':fingerprint,'updated_at':time.time()})
            self.report('starting', 90, '恢复 RD 和 SDK，验证真实查询')
            self.start()
            self.probe()
            (self.root/'maintenance.json').unlink(missing_ok=True)
            self.report('done', 100, '原始数据更新及服务验证完成；请单独同步本地行情', 'success')
        except Exception as exc:
            self.details['failed_phase'] = read_json(self.root/'status.json', {}).get('phase', 'unknown')
            self.stop()
            write_json(self.root/'version.json', {'status':'failed','version':None})
            self.report('failed', 0, '更新失败，本地源保持维护状态，项目库历史不受影响', 'failed', str(exc))
        finally:
            # A new task may be queued immediately after the terminal state.
            # Only remove this controller's claimed job, never the new request.
            (self.root/'active-request.json').unlink(missing_ok=True)
