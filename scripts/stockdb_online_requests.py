"""Validate structured inputs and build SDK queries without evaluating user code."""
import re
from datetime import datetime

from stockdb_online_catalog import BY_ID, REPORTS, NET_VALUES

class OnlineError(Exception):
    def __init__(self, message, status=400, retry_after=0):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after

def text(value, label):
    if not isinstance(value, str) or len(value) > 1000:
        raise OnlineError(f'{label}格式无效')
    return value.strip()

def integer(value, label, maximum=1000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise OnlineError(f'{label}应为 1 至 {maximum}')
    return value

def date(value, label, optional=False, timestamp=False):
    value = text(value, label)
    if not value and optional:
        return None
    pattern = '%Y-%m-%d %H:%M:%S' if timestamp else '%Y-%m-%d'
    try:
        parsed = datetime.strptime(value, pattern)
        if parsed.strftime(pattern) != value:
            raise ValueError()
    except ValueError:
        raise OnlineError(f'{label}格式无效')
    return value

def field_name(value, entry):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', value):
        raise OnlineError('查询字段名无效')
    # The published field list is illustrative, not a complete table schema.
    # Accept a single public identifier on this allowlisted table; the SDK/server
    # validates its existence. Dotted paths, private attributes and SQL are rejected.
    return value

def table_parameters(payload, entry):
    filters = payload.get('filters', [])
    if not isinstance(filters, list) or len(filters) > 10:
        raise OnlineError('最多设置10个筛选条件')
    result = []
    for condition in filters:
        if not isinstance(condition, dict):
            raise OnlineError('筛选条件格式无效')
        name = field_name(condition.get('field'), entry)
        op = condition.get('op', '==')
        if op not in ('==', '!=', '>', '>=', '<', '<=', 'in', 'like'):
            raise OnlineError('不支持的筛选运算符')
        value = condition.get('value')
        if op == 'in':
            if not isinstance(value, list) or not 1 <= len(value) <= 50:
                raise OnlineError('列表筛选应为1至50个值')
            values = value
        else:
            values = [value]
        if any(type(v) not in (str, int, float, bool) or len(str(v)) > 500 for v in values):
            raise OnlineError('筛选值必须是文本或数值')
        result.append(dict(field=name, op=op, value=value))
    columns = payload.get('fields', [])
    if not isinstance(columns, list) or len(columns) > 50:
        raise OnlineError('最多选择50个返回字段')
    columns = [field_name(v, entry) for v in columns]
    order = payload.get('order_field', '')
    if order:
        order = field_name(order, entry)
    direction = payload.get('order_direction', 'desc')
    if direction not in ('asc', 'desc'):
        raise OnlineError('排序方向无效')
    return dict(filters=result, fields=columns, limit=integer(payload.get('limit', 100), '返回条数', 5000),
                order_field=order, order_direction=direction)

def parameters(payload):
    if not isinstance(payload, dict):
        raise OnlineError('请求必须是对象')
    method = payload.get('method')
    if not isinstance(method, str) or method not in BY_ID:
        raise OnlineError('不支持的数据类型')
    entry = BY_ID[method]
    if entry['kind'] == 'table':
        return method, '', table_parameters(payload, entry)
    allowed = {f['name'] for f in entry['params']}
    code = text(payload.get('code', ''), '代码') if 'code' in allowed else ''
    if code and not re.fullmatch(r'[0-9]{6}', code):
        raise OnlineError('股票或基金代码应为六位数字')
    if any(f['name'] == 'code' and f['required'] for f in entry['params']) and not code:
        raise OnlineError('此接口需要股票或基金代码')
    args = {}
    for key, label in [('start_date', '开始日期'), ('end_date', '结束日期'), ('date', '查询日期')]:
        if key in allowed:
            descriptor = next(f for f in entry['params'] if f['name'] == key)
            value = date(payload.get(key, ''), label, optional=not descriptor['required'])
            if value:
                args[key] = value
    first = args.get('start_date', args.get('date'))
    if first and args.get('end_date') and first > args['end_date']:
        raise OnlineError('开始日期不能晚于结束日期')
    if 'count' in allowed:
        args['count'] = integer(payload.get('count', next(f['default'] for f in entry['params'] if f['name'] == 'count')), '条数')
    if method in ('get_last_tick', 'get_ticks', 'get_call_auction'):
        args['security'] = code
        if method == 'get_ticks':
            args['end_dt'] = date(payload.get('end_dt', ''), '截止时间', timestamp=True)
    elif method in ('get_fundamentals', 'get_fundamentals_continuously'):
        report = payload.get('report')
        if not isinstance(report, str) or report not in REPORTS:
            raise OnlineError('请选择报表或财务指标')
        args['report'] = report
        if method == 'get_fundamentals':
            quarter = text(payload.get('quarter', ''), '报告期')
            if not re.fullmatch(r'20[0-9]{2}q[1-4]', quarter):
                raise OnlineError('报告期格式为 2024q4')
            args['statDate'] = quarter
    elif method in ('get_mtss', 'get_money_flow', 'get_billboard_list', 'get_locked_shares'):
        args['security_list' if method in ('get_mtss', 'get_money_flow') else 'stock_list'] = [code] if code else None
    elif method == 'get_factor_values':
        codes = [v.strip() for v in text(payload.get('codes', ''), '股票列表').split(',')]
        factors = [v.strip() for v in text(payload.get('factors', ''), '因子列表').split(',')]
        if not 1 <= len(codes) <= 20 or any(not re.fullmatch(r'[0-9]{6}', v) for v in codes):
            raise OnlineError('股票列表应为1至20个六位代码')
        if not 1 <= len(factors) <= 20 or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', v) for v in factors):
            raise OnlineError('因子列表格式无效，最多20项')
        args.update(securities=codes, factors=factors)
    elif method == 'get_extras':
        if not isinstance(payload.get('info'), str) or payload['info'] not in NET_VALUES:
            raise OnlineError('只支持基金净值类型')
        args.update(info=payload['info'], security_list=[code])
    elif method in ('get_dominant_future', 'get_future_contracts'):
        symbol = text(payload.get('symbol', ''), '期货品种').upper()
        if not re.fullmatch(r'[A-Z]{1,8}', symbol):
            raise OnlineError('期货品种应为字母，例如 IF')
        args['underlying_symbol'] = symbol
    return method, code, args

def invoke(sdk, method, code, args):
    args = dict(args)
    if BY_ID[method]['kind'] == 'table':
        root, name = method.split('.')
        namespace = getattr(sdk, root)
        table = getattr(namespace, name)
        fields = [getattr(table, name) for name in args['fields']]
        q = sdk.query(*fields) if fields else sdk.query(table)
        for condition in args['filters']:
            field = getattr(table, condition['field'])
            value = condition['value']
            op = condition['op']
            if op == 'in': expr = field.in_(value)
            elif op == 'like': expr = field.like(value)
            elif op == '==': expr = field == value
            elif op == '!=': expr = field != value
            elif op == '>': expr = field > value
            elif op == '>=': expr = field >= value
            elif op == '<': expr = field < value
            else: expr = field <= value
            q = q.filter(expr)
        if args['order_field']:
            field = getattr(table, args['order_field'])
            q = q.order_by(field.asc() if args['order_direction'] == 'asc' else field.desc())
        return namespace.run_query(q.limit(args['limit']))
    if method in ('get_fundamentals', 'get_fundamentals_continuously'):
        table = getattr(sdk, args.pop('report'))
        q = sdk.query(table)
        if code:
            q = q.filter(table.code == code + ('.XSHG' if code.startswith('6') else '.XBSE' if code.startswith(('4', '8', '9')) else '.XSHE'))
        return getattr(sdk, method)(q, **args)
    return getattr(sdk, method)(**args)
