"""Shared, dependency-free contracts for the API and native SDK bridge."""
import json
from pathlib import Path

DEFINITIONS = json.loads(Path(__file__).with_name('indicator_catalog.json').read_text(encoding='utf-8'))
REGISTRY = {item['key']: item for item in DEFINITIONS}

def validate_parameters(name, chosen=None):
    if name not in REGISTRY:
        raise ValueError(f'unsupported indicator: {name}')
    definitions = REGISTRY[name]['parameters']
    if chosen is None:
        chosen = {}
    if not isinstance(chosen, dict) or chosen.keys() - {p['key'] for p in definitions}:
        raise ValueError('invalid indicator parameters')
    result = {}
    for p in definitions:
        value = chosen.get(p['key'], p['default'])
        values = value if p['type'] == 'integer_list' else [value]
        if not isinstance(values, list) or not values or any(type(v) is not int or not p['min'] <= v <= p['max'] for v in values):
            raise ValueError('指标参数须为范围内的整数')
        if p['type'] == 'integer_list' and (len(values) > p['max_items'] or len(set(values)) != len(values)):
            raise ValueError('MA周期须为1～6个不重复的整数')
        result[p['key']] = value
    return result
