"""Main overlay values must be identical to real native zb functions."""
import os
import sys
import math
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import calculate_indicator_rows, indicator_registry
SDK_DIR=os.environ.get('STOCKDB_TEST_SDK_DIR',r'D:\Free_stockdb\stockdb\pybao')
KEYS=['boll','ema','expma','bbi','wma','sma','dma']
CUSTOM={'boll':{'n':10,'p':2.5},'ema':{'n':9},'expma':{'n1':7,'n2':21},'bbi':{'m1':2,'m2':5,'m3':9,'m4':15},'wma':{'n':9},'sma':{'n':9,'m':2},'dma':{'a':.25}}
def rows(count,flat=False):
    return [dict(ts=str(i),close=10. if flat else 10.+(i*7)%19+(i%3)*.2) for i in range(count)]

@unittest.skipUnless(Path(SDK_DIR).is_dir(),'SDK not installed')
class MainOverlayTests(unittest.TestCase):
    def test_defaults_custom_short_and_flat_match_native(self):
        sys.path.insert(0,SDK_DIR)
        from zhibiao import zb
        registry=indicator_registry()
        for count in (1,3,80):
            for flat in (False,True):
                history=rows(count,flat)
                for params in ({},CUSTOM):
                    result=calculate_indicator_rows(SDK_DIR,dict(rows=history,names=KEYS,params=params))
                    self.assertEqual([r['ts'] for r in result],[r['ts'] for r in history])
                    for key in KEYS:
                        d=registry.REGISTRY[key]
                        args=registry.validate_parameters(key,params.get(key))
                        expected=getattr(zb,d['native'])([r['close'] for r in history],*args.values())
                        cols=expected if len(d['native_outputs'])>1 else [expected]
                        for field,col in zip(d['native_outputs'],cols):
                            self.assertEqual([r[field] for r in result],[float(v) if math.isfinite(v) else None for v in col])
                    self.assertNotIn('ema',history[0])
    def test_custom_parameters_change_every_overlay_and_boll_order(self):
        history=rows(80)
        default=calculate_indicator_rows(SDK_DIR,dict(rows=history,names=KEYS))
        custom=calculate_indicator_rows(SDK_DIR,dict(rows=history,names=KEYS,params=CUSTOM))
        for key in KEYS:
            fields=indicator_registry().REGISTRY[key]['native_outputs']
            self.assertTrue(any(a[f]!=b[f] and a[f] is not None and b[f] is not None for a,b in zip(default,custom) for f in fields),key)
        self.assertGreater(default[-1]['boll_upper'],default[-1]['boll_mid'])
        self.assertGreater(default[-1]['boll_mid'],default[-1]['boll_lower'])
    def test_invalid_and_boundary_parameters(self):
        bad=[('boll',{'p':0}),('boll',{'p':True}),('boll',{'p':float('inf')}),('dma',{'a':0}),('dma',{'a':1.01}),('dma',{'a':'0.2'}),('sma',{'n':5,'m':6}),('ema',{'n':10**400})]
        for key,params in bad:
            with self.assertRaises(ValueError): calculate_indicator_rows(SDK_DIR,dict(rows=rows(3),names=[key],params={key:params}))
        result=calculate_indicator_rows(SDK_DIR,dict(rows=rows(3),names=['dma'],params={'dma':{'a':1}}))
        self.assertEqual([r['dma'] for r in result],[r['close'] for r in rows(3)])
