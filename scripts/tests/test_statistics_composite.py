"""Real SDK contracts for statistics, fields, native cross signals and indices."""
from datetime import UTC, datetime
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import calculate_indicator_rows, calculate_composite_rows, indicator_registry

SDK_DIR = os.environ.get('STOCKDB_TEST_SDK_DIR', r'D:\Free_stockdb\stockdb\pybao')
STATS = ['std', 'sum', 'hhv', 'llv', 'ref']
CROSSES = 'macd kdj dmi trix emv dpo dfma mtm mass roc asi'.split()


def bars(count):
    return [dict(ts=str(i), open=19.+i%7, high=25.+i%11, low=15.+i%5,
                 close=20.+(i*7)%19, volume=1000.+(i*13)%127, amount=10000.+i*19) for i in range(count)]


@unittest.skipUnless(Path(SDK_DIR).is_dir(), 'SDK not installed')
class StatisticsCompositeTests(unittest.TestCase):
    def test_all_statistics_fields_parameters_short_and_null_match_native(self):
        sys.path.insert(0, SDK_DIR)
        from zhibiao import zb
        for count in (1, 3, 80):
            for n in (1, 7, 10000):
                for field in ('close', 'open', 'high', 'low', 'volume', 'amount'):
                    rows = bars(count)
                    result = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=STATS,
                        params={key: dict(n=n, field=field) for key in STATS}))
                    for key in STATS:
                        expected = getattr(zb, key.upper())([r[field] for r in rows], n)
                        self.assertEqual([r[key] for r in result], [float(v) if math.isfinite(v) else None for v in expected])
                    self.assertNotIn('std', rows[0])
        for key in ('ema', 'sma', 'wma', 'dma'):
            result = calculate_indicator_rows(SDK_DIR, dict(rows=bars(80), names=[key], params={key: {'field': 'open'}}))
            chosen = indicator_registry().validate_parameters(key)
            self.assertEqual([r[key] for r in result], [float(v) if math.isfinite(v) else None for v in getattr(zb, key.upper())([r['open'] for r in bars(80)], *chosen.values())])

    def test_cross_signals_match_raw_sdk_and_are_opt_in(self):
        sys.path.insert(0, SDK_DIR)
        from zhibiao import BATCH_CROSS
        for count in (1, 3, 160):
            rows = bars(count)
            for key in CROSSES:
                chosen = indicator_registry().validate_parameters(key)
                result = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=[key], params={key: {'cross': True}}))
                raw = BATCH_CROSS([key], [list(chosen.values())], [0]*count, list(range(count)),
                    *[[r[f] for r in rows] for f in ('open','high','low','close','volume')], False)
                self.assertEqual([r[key+'_cross'] for r in result], raw[3][raw[2].index('cross')])
                self.assertTrue(all(r[key+'_cross'] in (-1, 0, 1) for r in result))
                self.assertNotIn(key+'_cross', calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=[key]))[0])

    def test_composite_equal_custom_native_result_alignment_and_all_periods(self):
        sys.path.insert(0, SDK_DIR)
        for period, stamps, targets in (
            ('1d', [20250101,20250102,20250103], ['2025-01-01T00:00:00Z','2025-01-02T00:00:00Z','2025-01-03T00:00:00Z']),
            ('1w', [20250103,20250110,20250117], ['2025-01-03T00:00:00Z','2025-01-10T00:00:00Z','2025-01-17T00:00:00Z']),
            ('1mon', [20250131,20250228,20250331], ['2025-01-31T00:00:00Z','2025-02-28T00:00:00Z','2025-03-31T00:00:00Z']),
            ('15m', [20250102094500,20250102100000,20250102101500], ['2025-01-02T01:45:00Z','2025-01-02T02:00:00Z','2025-01-02T02:15:00Z'])):
            rows = [dict(ts=ts, close=999.) for ts in targets]
            prices = [10.,20.,40.,20.,10.,20.]
            def loader(codes, frequency, start, end, fq):
                self.assertEqual(codes, ['600519','300502'])
                self.assertEqual(frequency, '1M' if period == '1mon' else period)
                self.assertEqual(start, '20200101')
                self.assertEqual(fq, 'qfq')
                return ([0,0,0,1,1,1], stamps*2, prices, prices, prices, prices, [100.]*6, [1000.]*6, [1.]*6, [1.]*6)
            for mode, expected in [('equal',[None,1250.,2500.]), ('custom',[None,1625.,3250.])]:
                result=calculate_composite_rows(rows,dict(members=[dict(code='600519',weight=3),dict(code='300502',weight=1)],weighting=mode),period,loader)
                self.assertEqual([r['zhishu_close'] for r in result],expected)
                self.assertEqual([r['close'] for r in result],[999.]*3)
                self.assertEqual([r['zhishu_count'] for r in result],[None,2,2])
                self.assertNotIn('zhishu_close', rows[0])

    def test_index_missing_stock_and_invalid_controls(self):
        sys.path.insert(0, SDK_DIR)
        registry=indicator_registry()
        for name, params in [('std',{'field':'bad'}),('ema',{'field':'volume'}),('ma',{'field':'open'}),('rsi',{'cross':True}),('macd',{'cross':1}),('std',{'n':0}),('std',{'n':True})]:
            with self.assertRaises(ValueError): registry.validate_parameters(name,params)
        invalid=[{}, {'members':[]}, {'members':[{'code':'600519','weight':-1}]},
                 {'members':[{'code':'600519'},{'code':'600519'}]}, {'members':[{'code':'600519','weight':0}],'weighting':'custom'},
                 {'members':[{'code':'600519','weight':True}]}, {'members':[{'code':'600519'}],'base':float('inf')},
                 {'members':[{'code':'600519'}],'start':'2020-02-31'}, {'members':[{'code':'600519'}],'start':'2999-01-01'}]
        for value in invalid:
            with self.assertRaises(ValueError): registry.validate_parameters('zhishu',value)
        with self.assertRaises(ValueError):
            calculate_composite_rows([{'ts':'2025-01-01T00:00:00Z'}], {'members':[{'code':'600519'}]}, '1d', lambda *a: ([],)*10)
        def no_query(*a):
            self.fail('An index starting after the viewport must not query historical inputs')
        result=calculate_composite_rows([{'ts':'2025-01-01T00:00:00Z'}],
            {'members':[{'code':'600519'}],'start':'2025-02-01'}, '1d', no_query)
        self.assertIsNone(result[0]['zhishu_close'])

    def test_zero_weight_exclusion_and_partial_members_match_native(self):
        sys.path.insert(0, SDK_DIR)
        from zhibiao import ZHISHU
        rows=[{'ts':f'2025-01-0{i}T00:00:00Z'} for i in (1,2,3)]
        def one_stock(codes,*args):
            self.assertEqual(codes,['300502'])
            prices=[20.,10.,20.]
            return ([0]*3,[20250101,20250102,20250103],prices,prices,prices,prices,[100.]*3,[1000.]*3,[1.]*3,[1.]*3)
        result=calculate_composite_rows(rows,{'members':[{'code':'600519','weight':0},{'code':'300502','weight':1}],'weighting':'custom'},'1d',one_stock)
        self.assertEqual([r['zhishu_close'] for r in result],[None,500.,1000.])
        self.assertEqual([r['zhishu_count'] for r in result],[None,1,1])
        prices=[10.,20.,40.,20.,20.]
        arrays=([0,0,0,1,1],[20250101,20250102,20250103,20250102,20250103],prices,prices,prices,prices,[100.]*5,[1000.]*5,[1.]*5,[1.]*5)
        raw=ZHISHU(*arrays)
        expected={str(d):(raw[4][i],raw[8][i]) for i,d in enumerate(raw[0])}
        result=calculate_composite_rows(rows,{'members':[{'code':'600519'},{'code':'300502'}]},'1d',lambda *a:arrays)
        for day,row in zip(['20250101','20250102','20250103'],result):
            self.assertEqual((row['zhishu_close'],row['zhishu_count']),expected.get(day,(None,None)))

    def test_local_snapshot_change_discards_index(self):
        sys.path.insert(0, SDK_DIR)
        prices=[10.,20.]
        arrays=([0,0],[20250101,20250102],prices,prices,prices,prices,[100.]*2,[1000.]*2,[1.]*2,[1.]*2)
        with patch.dict(os.environ,{'STOCKDB_CONTROL_DIR':'test-only-control'}), \
             patch('stockdb_sdk_bridge.ensure_available'), \
             patch('stockdb_sdk_bridge.data_version',side_effect=[1,2]):
            with self.assertRaisesRegex(RuntimeError,'数据版本已切换'):
                calculate_composite_rows([{'ts':'2025-01-02T00:00:00Z'}],{'members':[{'code':'600519'}]},'1d',lambda *a:arrays)
