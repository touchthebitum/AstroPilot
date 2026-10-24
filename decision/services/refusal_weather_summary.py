"""Presentation evidence only; never changes acquisition eligibility."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite

from decision.weather.provider_reliability import WeatherVariable


@dataclass(frozen=True)
class RefusalWeatherSummary:
    window_start: str
    window_end: str
    cloud_cover_min: float
    cloud_cover_max: float
    retrieved_at_utc: str
    provider: str


def refusal_weather_summary(result):
    if result.creation_refusal != 'no_eligible_acquisition_intent':
        return None
    candidate = result.recommendation.opportunity.candidate if result.recommendation else None
    assessments = [a for a in getattr(candidate, 'acquisition_intent_assessments', ())
                   if 'intent_not_targeted_by_project' not in a.reason_codes]
    if not assessments or any(a.reason_codes != ('insufficient_actionable_productive_window',)
                              for a in assessments):
        return None
    evaluation = (result.night or {}).get('object_evaluations', {}).get(candidate.catalog_key, {})
    window = evaluation.get('window') or {}
    start, end = window.get('start'), window.get('end')
    if any(not isinstance(t, datetime) or t.utcoffset() is None
           or t.minute or t.second or t.microsecond for t in (start, end)):
        return None
    start_utc, end_utc = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if not timedelta(0) < end_utc - start_utc <= timedelta(days=1):
        return None
    expected = set()
    cursor = start_utc
    while cursor < end_utc:
        expected.add(cursor)
        cursor += timedelta(hours=1)
    found = {}
    sources = set()
    for point in getattr(result.forecast_evidence, 'forecast_points', ()):
        instant = point.forecast_for_utc.astimezone(timezone.utc)
        if instant not in expected:
            continue
        for value in point.values:
            if value.variable != WeatherVariable.CLOUD_COVER_PERCENT:
                continue
            amount = value.value
            if (isinstance(amount, bool) or not isinstance(amount, (int, float))
                    or not isfinite(amount) or not 0 <= amount <= 100 or instant in found):
                return None
            found[instant] = float(amount)
            sources.add((point.provider_id, point.retrieved_at_utc.isoformat()))
    if set(found) != expected or len(sources) != 1:
        return None
    provider, retrieved = sources.pop()
    return RefusalWeatherSummary(start.isoformat(), end.isoformat(),
                                min(found.values()), max(found.values()), retrieved, provider)
