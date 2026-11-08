"""Compare common indicator adapters against the actual installed zb_core."""
import inspect
import math
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import calculate_indicator_rows, indicator_registry
SDK_DIR = os.environ.get('STOCKDB_TEST_SDK_DIR', r'D:\Free_stockdb\stockdb\pybao')
CUSTOM = {'rsi': {'n':7}, 'wr': {'n':14,'n1':5}, 'cci': {'n':9}, 'atr': {'n':6}}

def history(count):
    return [dict(ts=str(i),open=10+(i*7)%19,close=10.+(i*7)%19+(i%3)*.2,high=12.+(i*7)%19+(i%3)*.2,low=9.+(i*7)%19+(i%3)*.2,volume=100+i,amount=1000+i) for i in range(count)]

@unittest.skipUnless(Path(SDK_DIR).is_dir(), 'official SDK not installed')
class CommonIndicatorTests(unittest.TestCase):
    def test_native_defaults_custom_parameters_and_short_history(self):
        sys.path.insert(0,SDK_DIR)
        from zhibiao import zb
        registry=indicator_registry()
        for count in (1,3,12,80):
            rows=history(count)
            for custom in (False,True):
                params=CUSTOM if custom else {}
                result=calculate_indicator_rows(SDK_DIR,dict(rows=rows,names=list(CUSTOM),params=params))
                self.assertEqual([r['ts'] for r in result],[r['ts'] for r in rows])
                for key in CUSTOM:
                    d=registry.REGISTRY[key]
                    chosen=registry.validate_parameters(key,params.get(key))
                    signature=inspect.signature(getattr(zb,d['native']))
                    self.assertEqual([p.default for p in signature.parameters.values() if p.default is not inspect.Parameter.empty], [p['default'] for p in d['parameters']])
                    expected=getattr(zb,d['native'])(*[[r[f] for r in rows] for f in d['inputs']],*chosen.values())
                    columns=expected if len(d['native_outputs'])>1 else [expected]
                    for field,values in zip(d['native_outputs'],columns):
                        self.assertEqual([r[field] for r in result],[float(v) if math.isfinite(v) else None for v in values])
                self.assertNotIn('rsi',rows[0])

    def test_parameters_change_results_without_changing_sdk_scale(self):
        rows=history(80)
        default=calculate_indicator_rows(SDK_DIR,dict(rows=rows,names=list(CUSTOM)))
        custom=calculate_indicator_rows(SDK_DIR,dict(rows=rows,names=list(CUSTOM),params=CUSTOM))
        for field in ('rsi','wr1','wr2','cci','atr'):
            self.assertTrue(any(a[field] != b[field] and a[field] is not None and b[field] is not None for a,b in zip(default,custom)),field)
        for row in default:
            for field in ('rsi','wr1','wr2'):
                self.assertTrue(row[field] is None or 0 <= row[field] <= 100)

    def test_invalid_parameters_rejected_before_native_call(self):
        for key in CUSTOM:
            for value in (0,10001,True,1.5,'14'):
                with self.assertRaises(ValueError):
                    calculate_indicator_rows(SDK_DIR,dict(rows=history(3),names=[key],params={key:{'n':value}}))
