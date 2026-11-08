"""Local interface metadata, based on the public StockDB catalog (2026-11-07)."""
import json
from pathlib import Path

REPORTS = {'cash_flow': '现金流量表', 'income': '利润表', 'balance': '资产负债表', 'indicator': '财务指标'}
NET_VALUES = {'unit_net_value': '基金单位净值', 'acc_net_value': '基金累计净值', 'adj_net_value': '场外基金复权净值'}

def field(name, label, kind='text', required=True, **kwargs):
    return dict(name=name, label=label, type=kind, required=required, **kwargs)

CODE = field('code', '股票 / 基金代码', placeholder='六位代码，例如 000001')
OPTIONAL_CODE = field('code', '股票代码（留空查询全市场）', required=False, placeholder='留空或填写六位代码')
START = field('start_date', '开始日期', 'date')
END = field('end_date', '结束日期', 'date')
DATE = field('date', '查询日期（留空取最新）', 'date', required=False)
COUNT = field('count', '返回条数', 'number', default=20, min=1, max=1000)
REPORT = field('report', '报表 / 指标', 'select', default='cash_flow', options=REPORTS)
SYMBOL = field('symbol', '期货品种', placeholder='例如 IF、AU、RB')

def item(method, title, group, params):
    return dict(id=method, title=title, group=group, kind='api', params=params,
                coverage='按需手动请求；接口错误如实返回，不自动重试')

DIRECT = [
    item('get_last_tick', '实时逐笔', '实时逐笔', [CODE, COUNT]),
    item('get_ticks', '历史逐笔', '历史逐笔', [CODE, COUNT, field('end_dt', '截止时间', 'datetime-local')]),
    item('get_fundamentals', '单报告期财报与指标', '财务数据', [OPTIONAL_CODE, REPORT, field('quarter', '报告期', default='2024q4', placeholder='例如 2024q4')]),
    item('get_fundamentals_continuously', '连续多日财务数据', '财务数据', [OPTIONAL_CODE, REPORT, END, field('count', '连续交易日数', 'number', default=5, min=1, max=1000)]),
    item('get_billboard_list', '龙虎榜', '龙虎榜', [OPTIONAL_CODE, START, END]),
    item('get_locked_shares', '限售解禁', '限售解禁', [CODE, START, END]),
    item('get_money_flow', '资金流向', '资金流向', [CODE, START, END]),
    item('get_mtss', '两融交易数据', '融资融券', [CODE, START, END]),
    item('get_margincash_stocks', '融资标的名单', '融资融券', [DATE]),
    item('get_marginsec_stocks', '融券标的名单', '融资融券', [DATE]),
    item('get_call_auction', '集合竞价', '集合竞价', [CODE, START, END]),
    item('get_factor_values', '因子值', '因子数据', [field('codes', '股票代码列表', placeholder='000001,600000，最多20只'), field('factors', '因子名称列表', placeholder='pe_ratio,pb_ratio，最多20项'), START, END]),
    item('get_extras', '基金净值（补充接口）', '基金与 ETF', [CODE, field('info', '净值类型', 'select', default='unit_net_value', options=NET_VALUES), START, END]),
    item('get_dominant_future', '期货主力合约', '期货', [SYMBOL, DATE, field('end_date', '结束日期（可选，查询主力历史）', 'date', required=False)]),
    item('get_future_contracts', '期货合约名单', '期货', [SYMBOL, DATE]),
]
TABLES = json.loads(Path(__file__).with_name('stockdb_online_tables.json').read_text(encoding='utf-8'))
CATALOG = DIRECT + TABLES
BY_ID = {entry['id']: entry for entry in CATALOG}

def catalog():
    return {'source': 'https://dns.novapi.cc/docs/index.html', 'entries': CATALOG,
            'minimum_interval_seconds': 40, 'default_interval_seconds': 40}
