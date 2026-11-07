"""Shared, dependency-free contracts for the API and native SDK bridge."""
import json
import math
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
        def valid(v):
            numeric = type(v) in (int, float) if p['type'] == 'number' else type(v) is int
            return numeric and (v > p['min'] if p.get('exclusive_min') else v >= p['min']) and v <= p['max'] and math.isfinite(v)
        if not isinstance(values, list) or not values or not all(valid(v) for v in values):
            raise ValueError('指标参数须符合类型及范围要求')
        if p['type'] == 'integer_list' and (len(values) > p['max_items'] or len(set(values)) != len(values)):
            raise ValueError('MA周期须为1～6个不重复的整数')
        result[p['key']] = value
    for constraint in REGISTRY[name].get('constraints', []):
        if constraint['op'] == 'le' and result[constraint['left']] > result[constraint['right']]:
            raise ValueError('权重不可大于周期')
    return result
