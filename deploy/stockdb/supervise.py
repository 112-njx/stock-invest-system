"""Keep update control alive while the native data readers are stopped."""
import fcntl
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from stockdb_files import read_json, write_json
from update_control import Controller

children = []
stopping = False


def stop(signum, frame):
    global stopping
    stopping = True


def stop_readers():
    for child in reversed(children):
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    children.clear()


def start_readers():
    if stopping:
        raise RuntimeError('container is stopping')
    children.append(subprocess.Popen(['/opt/stockdb/stockdb', '/opt/stockdb/stockdb.conf'], start_new_session=True))
    deadline = time.monotonic() + 60
    while True:
        if stopping or children[0].poll() is not None:
            raise RuntimeError('RD startup interrupted or failed')
        try:
            with socket.create_connection(('127.0.0.1', 7899), timeout=1):
                break
        except OSError:
            if time.monotonic() > deadline:
                raise TimeoutError('RD startup timeout')
            time.sleep(.25)
    children.append(subprocess.Popen(['python', '/opt/stockdb_sdk_bridge.py', '--sdk-dir', '/opt/stockdb/pybao'], start_new_session=True))


def probe():
    deadline = time.monotonic() + 180
    while True:
        try:
            with urlopen('http://127.0.0.1:7900/ready', timeout=30) as r:
                assert r.status == 200
            with urlopen('http://127.0.0.1:7900/indicators/ready', timeout=30) as r:
                assert r.status == 200
            return
        except Exception:
            if stopping or time.monotonic() > deadline:
                raise RuntimeError('RD/SDK query verification failed')
            time.sleep(1)


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    root = Path(os.environ.get('STOCKDB_CONTROL_DIR', '/stockdb-control'))
    root.mkdir(parents=True, exist_ok=True)
    lock = (root/'linux-controller.lock').open('a+b')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    controller = Controller(root, '/opt/stockdb', start_readers, stop_readers, probe)
    controller.recover()
    def heartbeat():
        while not stopping:
            write_json(root/'heartbeat.json', {'time':time.time(), 'pid':os.getpid(), 'kind':'linux-container'})
            time.sleep(5)
    threading.Thread(target=heartbeat, daemon=True).start()
    worker = None
    try:
        if not (root/'maintenance.json').exists():
            start_readers()
        while not stopping:
            if worker is None or not worker.is_alive():
                job = read_json(root/'request.json')
                if job:
                    worker = threading.Thread(target=controller.execute, args=(job,), daemon=True)
                    worker.start()
                elif not (root/'maintenance.json').exists():
                    for child in children:
                        if child.poll() is not None:
                            raise RuntimeError('native reader exited')
            time.sleep(.25)
    finally:
        stop_readers()


if __name__ == '__main__':
    main()
