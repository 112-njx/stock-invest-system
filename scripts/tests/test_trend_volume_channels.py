"""Compare all batch 5–7 columns with the installed native SDK, including BATCH names."""
import inspect
import math
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import calculate_indicator_rows, indicator_registry

SDK_DIR = os.environ.get('STOCKDB_TEST_SDK_DIR', r'D:\Free_stockdb\stockdb\pybao')
KEYS = 'dmi trix dfma mass vr cr emv brar obv mfi asi taq ktn xsii'.split()
CUSTOM = {
    'dmi': {'m1': 9, 'm2': 3}, 'trix': {'m1': 7, 'm2': 9},
    'dfma': {'n1': 5, 'n2': 21, 'm': 6}, 'mass': {'n1': 5, 'n2': 12, 'm': 3},
    'vr': {'m1': 12}, 'cr': {'n': 9}, 'emv': {'n': 7, 'm': 3},
    'brar': {'m1': 12}, 'obv': {}, 'mfi': {'n': 7},
    'asi': {'m1': 12, 'm2': 5}, 'taq': {'n': 9},
    'ktn': {'n': 9, 'm': 5}, 'xsii': {'n': 104, 'm': 5},
}
# Independent output contract from zb_core.BATCH. Adapter fields are namespaced
# where the SDK's generic names (e.g. MASS "ma") would collide with other panels.
BATCH_FIELDS = {
    'dmi': ['pdi', 'mdi', 'adx', 'adxr'], 'trix': ['trix', 'trma'],
    'dfma': ['dfma_dif', 'dfma_difma'], 'mass': ['mass', 'ma'], 'vr': ['vr'],
    'cr': ['cr'], 'emv': ['emv', 'maemv'], 'brar': ['ar', 'br'], 'obv': ['obv'],
    'mfi': ['mfi'], 'asi': ['asi', 'asit'],
    'taq': ['taq_up', 'taq_mid', 'taq_down'],
    'ktn': ['ktn_up', 'ktn_mid', 'ktn_down'], 'xsii': ['td1', 'td2', 'td3', 'td4'],
}


def history(count, flat=False, zero_volume=False):
    closes = [20. if flat else 20. + (i * 7) % 19 + (i % 3) * .2 for i in range(count)]
    return [dict(ts=str(i), open=c if flat else c - .5, close=c,
                 high=c if flat else c + 2 + (i % 5) * .3,
                 low=c if flat else c - 1 - (i % 3) * .2,
                 volume=0. if zero_volume else 1000. + (i * 13) % 127)
            for i, c in enumerate(closes)]


def finite(values):
    return [float(v) if math.isfinite(v) else None for v in values]


@unittest.skipUnless(Path(SDK_DIR).is_dir(), 'SDK not installed')
class TrendVolumeChannelTests(unittest.TestCase):
    def test_every_column_defaults_custom_short_flat_zero_volume(self):
        sys.path.insert(0, SDK_DIR)
        from zhibiao import zb
        registry = indicator_registry()
        for count in (1, 3, 20, 180):
            for flat, zero_volume in ((False, False), (True, False), (False, True)):
                rows = history(count, flat, zero_volume)
                for params in ({}, CUSTOM):
                    result = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=KEYS, params=params))
                    self.assertEqual([r['ts'] for r in result], [r['ts'] for r in rows])
                    for key in KEYS:
                        d = registry.REGISTRY[key]
                        native = getattr(zb, d['native'])
                        chosen = registry.validate_parameters(key, params.get(key))
                        signature = inspect.signature(native)
                        self.assertEqual(list(signature.parameters)[:len(d['inputs'])],
                                         ['vol' if f == 'volume' else f for f in d['inputs']])
                        defaults = {p.name: p.default for p in signature.parameters.values()
                                    if p.default is not inspect.Parameter.empty}
                        self.assertTrue(all(chosen_key in defaults and defaults[chosen_key] == p['default']
                                            for p in d['parameters'] for chosen_key in [p['key']]
                                            if key != 'taq'))
                        raw = native(*[[r[f] for r in rows] for f in d['inputs']], *chosen.values())
                        columns = raw if isinstance(raw, tuple) else [raw]
                        self.assertEqual(len(columns), len(d['native_outputs']), key)
                        for field, column in zip(d['native_outputs'], columns):
                            self.assertEqual([r[field] for r in result], finite(column), (key, field, count))
                    self.assertNotIn('dmi_pdi', rows[0])

    def test_native_batch_output_names_order_and_taq_default(self):
        sys.path.insert(0, SDK_DIR)
        from zhibiao import BATCH
        rows = history(180)
        for params in ({}, CUSTOM):
            actual = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=KEYS, params=params))
            for key in KEYS:
                d = indicator_registry().REGISTRY[key]
                chosen = list(indicator_registry().validate_parameters(key, params.get(key)).values()) if params else []
                _, _, names, cols = BATCH([key], [chosen], [0] * len(rows), list(range(len(rows))),
                                          *[[r[f] for r in rows] for f in ('open', 'high', 'low', 'close', 'volume')])
                self.assertEqual(names, BATCH_FIELDS[key])
                self.assertEqual(len(names), len(d['native_outputs']))
                for field, col in zip(d['native_outputs'], cols):
                    self.assertEqual([r[field] for r in actual], finite(col), (key, field))

    def test_custom_changes_results_and_channels_keep_native_price_order(self):
        rows = history(180)
        default = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=KEYS))
        custom = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=KEYS, params=CUSTOM))
        for key in KEYS:
            if key == 'obv':  # The native OBV function has no configurable parameters.
                continue
            fields = indicator_registry().REGISTRY[key]['native_outputs']
            self.assertTrue(any(a[f] is not None and b[f] is not None and a[f] != b[f]
                                for a, b in zip(default, custom) for f in fields), key)
        for key in ('taq', 'ktn'):
            self.assertGreater(default[-1][key + '_up'], default[-1][key + '_mid'])
            self.assertGreater(default[-1][key + '_mid'], default[-1][key + '_down'])

    def test_all_parameter_validation_and_boundaries(self):
        registry = indicator_registry()
        for key in KEYS:
            for param in registry.REGISTRY[key]['parameters']:
                for invalid in (0, 10001, True, 1.5, '12'):
                    with self.assertRaises(ValueError):
                        calculate_indicator_rows(SDK_DIR, dict(rows=history(3), names=[key], params={key: {param['key']: invalid}}))
            for boundary in (1, 10000):
                params = {p['key']: boundary for p in registry.REGISTRY[key]['parameters']}
                result = calculate_indicator_rows(SDK_DIR, dict(rows=history(3), names=[key], params={key: params}))
                self.assertEqual(len(result), 3)
                for field in registry.REGISTRY[key]['native_outputs']:
                    self.assertTrue(all(r[field] is None or math.isfinite(r[field]) for r in result))
        with self.assertRaises(ValueError):
            calculate_indicator_rows(SDK_DIR, dict(rows=history(3), names=['obv'], params={'obv': {'n': 7}}))
