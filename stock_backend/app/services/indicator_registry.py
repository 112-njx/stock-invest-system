"""Shared, dependency-free contracts for the API and native SDK bridge."""
import json
import math
import re
from datetime import date
from pathlib import Path

DEFINITIONS = json.loads(Path(__file__).with_name('indicator_catalog.json').read_text(encoding='utf-8'))
REGISTRY = {item['key']: item for item in DEFINITIONS}

def validate_composite(chosen):
    if not isinstance(chosen, dict) or chosen.keys() - {'members', 'weighting', 'base', 'start'}:
        raise ValueError('无效的合成指数配置')
    members = chosen.get('members', [])
    if not isinstance(members, list) or not 1 <= len(members) <= 20:
        raise ValueError('合成指数须选择1～20只股票')
    codes = set()
    for member in members:
        if not isinstance(member, dict) or member.keys() - {'code', 'weight'}:
            raise ValueError('无效的股票权重')
        code, weight = member.get('code'), member.get('weight', 1)
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code) or code in codes:
            raise ValueError('股票代码须为不重复的六位数字')
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 1000000:
            raise ValueError('权重须为0～1000000的有限数值')
        codes.add(code)
    weighting = chosen.get('weighting', 'equal')
    if weighting not in ('equal', 'custom') or (weighting == 'custom' and not any(m.get('weight', 1) > 0 for m in members)):
        raise ValueError('自定义权重之和须大于零')
    base = chosen.get('base', 1000)
    if type(base) not in (int, float) or not math.isfinite(base) or not 0 < base <= 1000000000:
        raise ValueError('指数基点须大于0且不超过1000000000')
    start = chosen.get('start', '2020-01-01')
    try:
        day = date.fromisoformat(start)
        if day.isoformat() != start or not date(1990, 1, 1) <= day <= date.today():
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('起算日期须在1990年与今天之间') from None
    return dict(members=[dict(code=m['code'], weight=m.get('weight', 1)) for m in members],
                weighting=weighting, base=base, start=start)

def validate_controls(name, chosen=None):
    chosen = chosen or {}
    definition = REGISTRY[name]
    field = chosen.get('field', 'close')
    if not isinstance(field, str) or field not in definition.get('input_fields', ['close']):
        raise ValueError('该指标不支持所选输入字段')
    cross = chosen.get('cross', False)
    if type(cross) is not bool or (cross and not definition.get('cross', False)):
        raise ValueError('该指标不支持交叉信号')
    return field, cross

def validate_parameters(name, chosen=None):
    if name not in REGISTRY:
        raise ValueError(f'unsupported indicator: {name}')
    if name == 'zhishu':
        return validate_composite(chosen)
    definitions = REGISTRY[name]['parameters']
    if chosen is None:
        chosen = {}
    if not isinstance(chosen, dict) or chosen.keys() - ({p['key'] for p in definitions} | {'field', 'cross'}):
        raise ValueError('invalid indicator parameters')
    validate_controls(name, chosen)
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
