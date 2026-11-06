"""Readiness probes real SDK data and reuses the normal short-lived cache."""
import json
from urllib.request import urlopen

with urlopen('http://127.0.0.1:7900/ready', timeout=180) as response:
    assert json.load(response)['status'] == 'ready'

with urlopen('http://127.0.0.1:7900/indicators/ready', timeout=45) as response:
    assert json.load(response)['status'] == 'ok'
