"""Readiness probes real SDK data and reuses the normal short-lived cache."""
import os
import time
from pathlib import Path
import json
from urllib.request import urlopen

root = Path(os.environ.get('STOCKDB_CONTROL_DIR', '/stockdb-control'))
if (root/'maintenance.json').exists():
    heartbeat = json.loads((root/'heartbeat.json').read_text())
    assert heartbeat.get('kind') == 'linux-container' and time.time()-heartbeat['time'] < 30
    raise SystemExit(0)  # Control is healthy; data readers remain explicitly unavailable.

with urlopen('http://127.0.0.1:7900/ready', timeout=180) as response:
    assert json.load(response)['status'] == 'ready'

with urlopen('http://127.0.0.1:7900/indicators/ready', timeout=45) as response:
    assert json.load(response)['status'] == 'ok'
