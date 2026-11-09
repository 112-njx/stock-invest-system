"""One indicator contract over the vendor and project-native Python modules."""
import json
import math
from datetime import date


def calculate_forecast(rows, checkpoint, expected_version):
    from market_indicators import FEATURE_VERSION, calculate

    if FEATURE_VERSION != expected_version:
        raise RuntimeError('forecast indicator version mismatch')
    bars = [(date.fromisoformat(row['ts'][:10]).toordinal(),
             *(float(row[field]) for field in ('open', 'high', 'low', 'close', 'volume')))
            for row in rows]
    features, checkpoint = calculate(bars, checkpoint)
    for row, item in zip(rows, json.loads(features), strict=True):
        for pivot in item['confirmed_pivots']:
            pivot['session'] = date.fromordinal(pivot.pop('day')).isoformat()
        if item['pullback'] is not None:
            pullback = item['pullback']
            pullback['from_session'] = date.fromordinal(pullback.pop('from_day')).isoformat()
        row['forecast_features'] = item
    return checkpoint


def calculate_rows(payload, registry, composite):
    rows, names, params = payload['rows'], payload['names'], payload.get('params') or {}
    forecast = registry.FORECAST_FEATURES
    if not isinstance(rows, list) or not 1 <= len(rows) <= registry.MAX_HISTORY_ROWS:
        raise ValueError('invalid history length')
    if not isinstance(names, list) or not names or any(
        not isinstance(name, str) or (name != forecast and name not in registry.REGISTRY)
        for name in names
    ):
        raise ValueError('unsupported indicator')
    if len(set(names)) != len(names):
        raise ValueError('duplicate indicator')
    if not isinstance(params, dict):
        raise ValueError('invalid parameters')

    checkpoint = payload.get('checkpoint')
    return_checkpoint = payload.get('return_checkpoint', False)
    if type(return_checkpoint) is not bool or (
        (return_checkpoint or checkpoint is not None) and names != [forecast]
    ) or (checkpoint is not None and (not return_checkpoint or not isinstance(checkpoint, str)
                                       or len(checkpoint) > 32_768)):
        raise ValueError('invalid incremental indicator request')

    if any(name != forecast for name in names):
        from zhibiao import zb

    def array(field):
        values = [float(row[field]) for row in rows]
        if not all(math.isfinite(value) for value in values):
            raise ValueError('nonfinite input')
        return values

    output = [dict(row) for row in rows]

    def append(fields, series):
        for field, values in zip(fields, series, strict=True):
            if len(values) != len(rows):
                raise ValueError('native output length mismatch')
            for row, value in zip(output, values):
                row[field] = float(value) if math.isfinite(value) else None

    for name in names:
        if name == forecast:
            if (payload.get('period') != '1d' or len(rows) > registry.MAX_FORECAST_ROWS
                    or params.get(name)):
                raise ValueError('forecast features require bounded daily history and no parameters')
            checkpoint = calculate_forecast(output, checkpoint, registry.FORECAST_FEATURE_VERSION)
            continue

        definition = registry.REGISTRY[name]
        chosen = registry.validate_parameters(name, params.get(name))
        if name == 'zhishu':
            output = composite(output, chosen, payload.get('period'))
            continue

        field, cross = registry.validate_controls(name, params.get(name))
        if name == 'ma':
            close = array('close')
            periods = chosen['periods']
            append([f'ma{n}' for n in periods], [zb.MA(close, n) for n in periods])
        elif definition['native']:
            fields = definition['native_outputs']
            arguments = [array(field if key == 'close' and definition.get('input_fields') else key)
                         for key in definition['inputs']]
            raw = getattr(zb, definition['native'])(*arguments, *chosen.values())
            append(fields, raw if len(fields) > 1 else [raw])
        elif name == 'volume':
            volume = array('volume')
            append(('volume_ma5', 'volume_ma10'), [zb.MA(volume, n) for n in (5, 10)])
        if cross:
            from zhibiao import BATCH_CROSS
            raw = BATCH_CROSS([name], [list(chosen.values())], [0] * len(rows), list(range(len(rows))),
                              *[array(key) for key in ('open', 'high', 'low', 'close', 'volume')], False)
            append([name + '_cross'], [raw[3][raw[2].index('cross')]])

    return {'rows': output, 'checkpoint': checkpoint} if return_checkpoint else output
