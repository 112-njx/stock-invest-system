"""Momentum/strength adapters compared against actual zb_core, not local formulas."""
import inspect
import math
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import calculate_indicator_rows,indicator_registry
SDK_DIR=os.environ.get('STOCKDB_TEST_SDK_DIR',r'D:\Free_stockdb\stockdb\pybao')
KEYS=['bias','psy','dpo','mtm','roc']
CUSTOM={'bias':{'l1':3,'l2':9,'l3':18},'psy':{'n':9,'m':3},'dpo':{'m1':12,'m2':6,'m3':3},'mtm':{'n':7,'m':3},'roc':{'n':7,'m':3}}
def history(count,flat=False):
    return [dict(ts=str(i),close=10. if flat else 10.+(i*7)%19+(i%3)*.2) for i in range(count)]

@unittest.skipUnless(Path(SDK_DIR).is_dir(),'SDK not installed')
class MomentumIndicatorTests(unittest.TestCase):
    def test_defaults_custom_flat_and_short_match_every_native_column(self):
        sys.path.insert(0,SDK_DIR)
        from zhibiao import zb
        registry=indicator_registry()
        for count in (1,3,12,100):
            for flat in (False,True):
                rows=history(count,flat)
                for params in ({},CUSTOM):
                    result=calculate_indicator_rows(SDK_DIR,dict(rows=rows,names=KEYS,params=params))
                    self.assertEqual([r['ts'] for r in result],[r['ts'] for r in rows])
                    for key in KEYS:
                        d=registry.REGISTRY[key]
                        native=getattr(zb,d['native'])
                        signature=inspect.signature(native)
                        self.assertEqual([p.default for p in signature.parameters.values() if p.default is not inspect.Parameter.empty],[p['default'] for p in d['parameters']])
                        chosen=registry.validate_parameters(key,params.get(key))
                        expected=native([r['close'] for r in rows],*chosen.values())
                        self.assertEqual(len(expected),len(d['native_outputs']))
                        for field,column in zip(d['native_outputs'],expected):
                            self.assertEqual([r[field] for r in result],[float(v) if math.isfinite(v) else None for v in column])
                    self.assertNotIn('bias1',rows[0])
    def test_custom_changes_each_indicator_and_preserves_sign_and_scale(self):
        rows=history(100)
        default=calculate_indicator_rows(SDK_DIR,dict(rows=rows,names=KEYS))
        custom=calculate_indicator_rows(SDK_DIR,dict(rows=rows,names=KEYS,params=CUSTOM))
        for key in KEYS:
            fields=indicator_registry().REGISTRY[key]['native_outputs']
            self.assertTrue(any(a[f] is not None and b[f] is not None and a[f]!=b[f] for a,b in zip(default,custom) for f in fields),key)
        for field in ['bias1','dpo','mtm','roc']:
            finite=[r[field] for r in default if r[field] is not None]
            self.assertTrue(any(v<0 for v in finite));self.assertTrue(any(v>0 for v in finite))
        self.assertTrue(all(r['psy'] is None or 0<=r['psy']<=100 for r in default))
    def test_each_parameter_rejects_invalid_values(self):
        registry=indicator_registry()
        for key in KEYS:
            for p in registry.REGISTRY[key]['parameters']:
                for invalid in (0,10001,True,1.5,'12'):
                    with self.assertRaises(ValueError):calculate_indicator_rows(SDK_DIR,dict(rows=history(3),names=[key],params={key:{p['key']:invalid}}))

    def test_supported_period_boundaries_keep_output_length(self):
        registry=indicator_registry()
        for key in KEYS:
            for boundary in (1,10000):
                params={p['key']:boundary for p in registry.REGISTRY[key]['parameters']}
                result=calculate_indicator_rows(SDK_DIR,dict(rows=history(3),names=[key],params={key:params}))
                self.assertEqual(len(result),3)
                for field in registry.REGISTRY[key]['native_outputs']:
                    self.assertTrue(all(r[field] is None or math.isfinite(r[field]) for r in result))
