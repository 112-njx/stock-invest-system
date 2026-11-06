"""Probe the bridge, native SDK and stored data, not just the HTTP listener."""
import json
from urllib.request import urlopen

with urlopen('http://127.0.0.1:7900/kline?code=600519&frequency=1d&start=20240102&end=20240105', timeout=180) as response:
    rows = json.load(response)
assert isinstance(rows, list) and rows and all('close' in row for row in rows), rows
