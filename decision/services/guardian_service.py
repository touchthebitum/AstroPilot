"""Pure evaluation of caller-supplied evidence, independent of other engines."""
from datetime import datetime
import math
from decision.models.guardian import (
    GuardianAction, GuardianAssessment, GuardianEvidence, GuardianObservation,
    GuardianPolicy, GuardianRiskLevel as Risk,
)


def _valid(name: str, evidence: GuardianEvidence | None, now: datetime, policy: GuardianPolicy) -> bool:
    if not isinstance(evidence, GuardianEvidence):
        return False
    if evidence.provenance not in ('OBSERVATION', 'FORECAST') or not isinstance(evidence.source, str) or not evidence.source.strip():
        return False
    timestamp = evidence.timestamp
    if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
        return False
    if not 0 <= (now - timestamp).total_seconds() <= policy.max_age_seconds:
        return False
    value = evidence.value
    if name == 'rain_active':
        return type(value) is bool
    if name == 'rain_eta_minutes' and value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    if name == 'dew_spread_c':
        return True  # Negative spread is itself critical evidence.
    return value >= 0 and (name != 'humidity_percent' or value <= 100)


def assess_guardian(observation: GuardianObservation, *, now: datetime,
                    session_active: bool, policy: GuardianPolicy = GuardianPolicy()) -> GuardianAssessment:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('now must be timezone aware')
    if type(session_active) is not bool:
        raise ValueError('session_active must be explicit boolean')
    level = Risk.SAFE
    reasons = []
    complete = True
    sources = tuple((name, getattr(observation, name)) for name in observation.__dataclass_fields__)
    for name, evidence in sources:
        if not _valid(name, evidence, now, policy):
            complete = False
            reasons.append(name + ':missing_invalid_untrusted_or_stale')
            continue
        value = evidence.value
        channel_level = Risk.SAFE
        if name == 'rain_active' and value is True:
            channel_level = Risk.CRITICAL
        elif (name == 'rain_eta_minutes' and value is not None
              and value - (now - evidence.timestamp).total_seconds() / 60
              <= policy.rain_imminent_minutes):
            channel_level = Risk.CRITICAL
        elif name in ('wind_kmh', 'gust_kmh', 'humidity_percent', 'dew_spread_c'):
            prefix = {'wind_kmh': 'wind', 'gust_kmh': 'gust', 'humidity_percent': 'humidity', 'dew_spread_c': 'dew'}[name]
            for suffix, candidate in (('watch', Risk.WATCH), ('warning', Risk.WARNING), ('critical', Risk.CRITICAL)):
                threshold = getattr(policy, prefix + '_' + suffix)
                if (value <= threshold if prefix == 'dew' else value >= threshold):
                    channel_level = candidate
        if channel_level != Risk.SAFE:
            reasons.append(name + ':' + channel_level.name)
        level = max(level, channel_level)
    if not complete:
        level = Risk.UNKNOWN
    return GuardianAssessment(level, GuardianAction(level.value), tuple(reasons), complete,
                              complete, policy, now, sources, session_active)
