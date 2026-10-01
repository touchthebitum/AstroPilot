"""Descriptive counts and persisted errors, on an explicitly admitted population."""
from collections import Counter, defaultdict
from math import fsum, isfinite

UNITS = {'temperature_c': '°C', 'relative_humidity_percent': '%', 'wind_speed_kmh': 'km/h', 'cloud_cover_percent': '%'}


class OutcomeHistoryStatisticsUnavailable(ValueError):
    pass


def finite_mean(values):
    if not values:
        return None
    # Scale before summing: the exact mean of finite inputs is bounded by them.
    scale = max(abs(value) for value in values)
    mean = (fsum(value / scale for value in values) / len(values)) * scale if scale else 0.0
    if not isfinite(mean):
        raise OutcomeHistoryStatisticsUnavailable('nonfinite_statistics')
    return mean


def statistics(rows):
    def distinct(items):
        return {'n_observations': len({r['observation_id'] for r in items}),
                'n_decisions': len({r['decision_id'] for r in items if r['decision_id']}),
                'n_executions': len({r['execution_id'] for r in items if r['execution_id']})}
    coverage = {key: sum(r['status'] == key for r in rows) for key in ('comparable', 'partial', 'not_comparable')}
    variables = {}
    matrix = defaultdict(Counter)
    outcomes = Counter()
    reasons = defaultdict(set)
    for row in rows:
        codes = {reason['code'] for reason in row['reasons']}
        for result in row['results']:
            codes.update(reason['code'] for reason in result['reasons'])
            if result['variable'] == 'cloud_cover_percent' and result['status'] == 'comparable':
                matrix[result['predicted_condition']][result['observed_condition']] += 1
                outcomes[result['outcome']] += 1
        for code in codes:
            reasons[code].add(row['observation_id'])
    for variable, unit in UNITS.items():
        present = [(r, next((v for v in r['results'] if v['variable'] == variable), None)) for r in rows]
        comparable = [(r, v) for r, v in present if v and v['status'] == 'comparable' and v['unit'] == unit]
        item = {'unit': unit, 'error_unit': 'percentage_points' if variable == 'relative_humidity_percent' else unit,
                'n_comparable': len(comparable), 'n_not_comparable': sum(v is not None and v['status'] != 'comparable' for _, v in present),
                'n_absent': sum(v is None for _, v in present), **distinct([r for r, _ in comparable])}
        if variable != 'cloud_cover_percent':
            item.update(mean_signed_error=finite_mean([v['signed_error'] for _, v in comparable]),
                        mean_absolute_error=finite_mean([v['absolute_error'] for _, v in comparable]))
        variables[variable] = item
    return {'n_evaluations': len(rows), **distinct(rows), 'coverage': coverage, 'variables': variables,
            'clouds': {'n': sum(outcomes.values()), 'forecast_x_observed': {k: dict(v) for k, v in matrix.items()},
                       'match': outcomes['match'], 'mismatch': outcomes['mismatch']},
            'reason_observation_counts': {k: len(v) for k, v in sorted(reasons.items())}}
