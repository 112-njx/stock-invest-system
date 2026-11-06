"""Windows local helper. Executes only a fixed, locally configured updater and Compose service."""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stock_backend'))
from app.services.stockdb_files import manifest_fingerprint, read_json, write_json


def updater_alive(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5  # access denied is not proof of exit
    try:
        code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


class UpdateAgent:
    def __init__(self, workspace, stockdb, control, compose='deploy/docker-compose.dev.yml', runner=None):
        self.workspace, self.stockdb, self.control = map(Path, (workspace, stockdb, control))
        self.compose = compose
        self.runner = runner or subprocess.run
        self.control.mkdir(parents=True, exist_ok=True)

    def command(self, *args, timeout=180):
        result = self.runner(['docker', 'compose', '--env-file', '.env.docker', '-f', self.compose, *args],
                             cwd=self.workspace, capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-1500:])
        return result

    def report(self, task, phase, progress, message, status='running', error=None):
        write_json(self.control / 'status.json', dict(task_id=task, status=status, phase=phase,
                   progress=progress, message=message, error=error, updated_at=time.time()))

    def initialize(self):
        if not (self.control / 'version.json').exists() or (
            read_json(self.control / 'version.json', {}).get('status') == 'failed'
            and read_json(self.control / 'status.json', {}).get('task_id') is None
        ):
            fingerprint = manifest_fingerprint(self.stockdb)
            write_json(self.control / 'version.json', {'version': uuid4().hex, 'fingerprint': fingerprint,
                       'status': 'ready', 'updated_at': time.time(), 'origin': 'existing-local-data'})
            self.report(None, 'idle', 0, '现有本地数据已登记；尚未执行一键更新', 'idle')

    def execute(self, job):
        task = job['task_id']
        if job.get('operation') != 'update':
            raise ValueError('unsupported operation')
        (self.control / 'maintenance.json').touch(exist_ok=True)
        try:
            existing = read_json(self.control / 'updater-process.json')
            if existing and updater_alive(existing['pid']):
                raise RuntimeError('上次更新器仍在运行，请等待其退出')
            check = self.runner(['powershell', '-NoProfile', '-Command',
                                 '@(Get-Process stockdb,stockdb_server,数据更新 -ErrorAction SilentlyContinue).Count'],
                                capture_output=True, timeout=30)
            if check.returncode or check.stdout.strip() != b'0':
                raise RuntimeError('请先关闭宿主机 stockdb 服务和其他数据更新器')
            if not (self.stockdb / '数据更新.exe').is_file():
                raise RuntimeError('未找到本机数据更新.exe')
            self.report(task, 'stopping', 5, '停止 StockDB 容器；现有项目库历史仍可查看')
            self.command('stop', 'stockdb-local')
            write_json(self.control / 'version.json', {'status': 'updating', 'version': None})
            self.report(task, 'updating', 15, '执行本机数据更新.exe，下载原始文件；不创建备份')
            with (self.control / 'updater.log').open('wb') as log:
                process = subprocess.Popen([str(self.stockdb / '数据更新.exe')], cwd=self.stockdb,
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                write_json(self.control / 'updater-process.json', {'pid': process.pid})
                try:
                    code = process.wait(timeout=4 * 3600)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise TimeoutError('数据更新超过 4 小时，已停止更新器')
                finally:
                    (self.control / 'updater-process.json').unlink(missing_ok=True)
            if code:
                raise RuntimeError(f'更新器退出码 {code}，请检查本机 updater.log')
            self.report(task, 'verifying', 65, '按下载清单校验文件大小和 SHA-256，历史修正也生成新版本')
            last_report = [0.0]
            def progress(count):
                if time.monotonic() - last_report[0] > 3:
                    self.report(task, 'verifying', 70, f'正在校验原始文件，已校验 {count} 个')
                    last_report[0] = time.monotonic()
            fingerprint = manifest_fingerprint(self.stockdb, verify=True, progress=progress)
            write_json(self.control / 'version.json', {'version': uuid4().hex, 'status': 'ready',
                       'fingerprint': fingerprint, 'updated_at': time.time()})
            self.report(task, 'starting', 90, '启动服务并验证真实 SDK 查询；旧版本计算缓存不再使用')
            self.command('up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'stockdb-local', timeout=240)
            self.command('exec', '-T', 'stockdb-local', 'python', '/opt/healthcheck.py')
            (self.control / 'request.json').unlink(missing_ok=True)
            (self.control / 'maintenance.json').unlink(missing_ok=True)
            self.report(task, 'done', 100, '原始数据更新并验证完成；请点击“同步本地行情”导入项目数据库', 'success')
        except Exception as exc:
            write_json(self.control / 'version.json', {'status': 'failed', 'version': None, 'error': str(exc)})
            (self.control / 'request.json').unlink(missing_ok=True)
            # Never restart a possibly partial dataset or silently serve its former cache.
            self.report(task, 'failed', 0, '更新失败，本地源保持维护状态；项目库历史仍可查看，请检查日志后重试', 'failed', str(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stockdb-dir', default='D:/Free_stockdb/stockdb')
    parser.add_argument('--workspace', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--compose', default='deploy/docker-compose.dev.yml')
    args = parser.parse_args()
    root = Path(args.workspace) / 'stock_backend/data/stockdb-control'
    root.mkdir(parents=True, exist_ok=True)
    # Kernel lock releases after a crash; the lock file itself may remain.
    import msvcrt
    lock = (root / 'agent.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    agent = UpdateAgent(args.workspace, args.stockdb_dir, root, args.compose)
    def heartbeat():
        while True:
            existing = read_json(root / 'updater-process.json')
            if existing and not updater_alive(existing['pid']):
                (root / 'updater-process.json').unlink(missing_ok=True)
            write_json(root / 'heartbeat.json', {'time': time.time(), 'pid': os.getpid()})
            time.sleep(5)
    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        agent.initialize()
    except Exception as exc:
        write_json(root / 'version.json', {'status': 'failed', 'version': None})
        agent.report(None, 'failed', 0, '本地数据清单检查失败，请执行一键更新修复', 'failed', str(exc))
    previous = read_json(root / 'status.json', {})
    if previous.get('status') == 'running':
        # An interrupted updater might still be writing: never restart the DB here.
        write_json(root / 'version.json', {'status': 'failed', 'version': None})
        agent.report(previous.get('task_id'), 'failed', 0, '助手曾中断；请确认更新器已退出后重新更新', 'failed', 'interrupted host helper')
        (root / 'request.json').unlink(missing_ok=True)
    while True:
        job = read_json(root / 'request.json')
        if job:
            agent.execute(job)
        elif (root / 'maintenance.json').exists() and time.time() - (root / 'maintenance.json').stat().st_mtime > 30:
            state = read_json(root / 'status.json', {})
            if state.get('status') not in {'failed', 'running'}:
                write_json(root / 'version.json', {'status': 'failed', 'version': None})
                agent.report(state.get('task_id'), 'failed', 0, '更新请求提交中断，请重试原始数据更新', 'failed', 'incomplete update submission')
        time.sleep(1)


if __name__ == '__main__':
    main()
