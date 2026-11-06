"""Keep the native server and existing SDK bridge in one failure domain."""
import os
import signal
import socket
import subprocess
import time

children = []
stopping = False


def stop(signum, frame):
    global stopping
    stopping = True


def launch(args):
    process = subprocess.Popen(args, start_new_session=True)
    children.append(process)
    return process


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    for directory in ('data', 'data1', 'data_app', 'mydb'):
        if not os.path.isdir(directory):
            raise RuntimeError(f'Missing bind-mounted directory: {directory}')
    server = launch(['/opt/stockdb/stockdb', '/opt/stockdb/stockdb.conf'])
    deadline = time.monotonic() + 60
    try:
        while not stopping:
            if server.poll() is not None:
                raise RuntimeError(f'stockdb exited: {server.returncode}')
            try:
                with socket.create_connection(('127.0.0.1', 7899), timeout=1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('stockdb startup exceeded 60 seconds')
                time.sleep(.25)
        if not stopping:
            launch(['python', '/opt/stockdb_sdk_bridge.py', '--sdk-dir', '/opt/stockdb/pybao'])
        while not stopping:
            for child in children:
                if child.poll() is not None:
                    raise RuntimeError(f'Child exited: {child.args}, status={child.returncode}')
            time.sleep(.25)
    finally:
        for child in reversed(children):
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == '__main__':
    main()
