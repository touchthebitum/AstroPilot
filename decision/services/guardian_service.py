"""Pure evaluation of caller-supplied evidence, independent of other engines."""
from datetime import datetime
from enum import Enum
import math
from decision.models.guardian import (
    GuardianAction, GuardianAssessment, GuardianEvidence, GuardianObservation,
    GuardianPolicy, GuardianRiskLevel as Risk, GuardianSessionContext,
    GuardianSessionState as State, GuardianActionApplicability as Applicability,
)

from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.models.guardian_rain import GuardianRainUncertainty
from decision.services.guardian_live_contracts import live_session, rain_onset_valid


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
    if name == 'rain_eta_minutes' and isinstance(evidence, GuardianRainUncertainty):
        return rain_onset_valid(evidence)
    if name == 'rain_eta_minutes' and value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    if name == 'dew_spread_c':
        return True  # Negative spread is itself critical evidence.
    return value >= 0 and (name != 'humidity_percent' or value <= 100)


class _Unset(Enum):
    TOKEN = 'unset'


_UNSET = _Unset.TOKEN
_SESSION_MAX_AGE_SECONDS = 900


def _session(context: GuardianSessionContext | GuardianLiveSessionEvidence | None, now: datetime) -> tuple[State, Applicability, tuple[str, ...]]:
    if isinstance(context, GuardianLiveSessionEvidence):
        return live_session(context, now)
    if context is None:
        return State.UNKNOWN, Applicability.UNKNOWN, ('session_context:missing',)
    if (not isinstance(context, GuardianSessionContext)
            or context.version != 'guardian-session-v1'
            or type(context.session_active) is not bool
            or not isinstance(context.observed_at, datetime)
            or context.observed_at.utcoffset() is None
            or (context.session_id is not None and
                (not isinstance(context.session_id, str) or not context.session_id.strip()))):
        return State.UNKNOWN, Applicability.UNKNOWN, ('session_context:invalid',)
    if not 0 <= (now - context.observed_at).total_seconds() <= _SESSION_MAX_AGE_SECONDS:
        return State.UNKNOWN, Applicability.UNKNOWN, ('session_context:future_or_stale',)
    if context.session_active:
        return State.ACTIVE, Applicability.APPLICABLE, ()
    return State.INACTIVE, Applicability.NOT_APPLICABLE, ()


def assess_guardian(observation: GuardianObservation, *, now: datetime,
                    session_active: bool | _Unset = _UNSET,
                    session_context: GuardianSessionContext | GuardianLiveSessionEvidence | None | _Unset = _UNSET,
                    policy: GuardianPolicy = GuardianPolicy()) -> GuardianAssessment:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('now must be timezone aware')
    if session_active is not _UNSET:
        if session_context is not _UNSET:
            raise ValueError('Supply only one session context interface')
        if type(session_active) is not bool:
            raise ValueError('session_active must be explicit boolean')
        session_context = GuardianSessionContext(session_active, now)
    elif session_context is _UNSET:
        session_context = None
    state, applicability, session_reasons = _session(session_context, now)
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
    return GuardianAssessment(
        risk_level=level, action=GuardianAction(level.value), reasons=tuple(reasons),
        evidence_complete=complete, decision_eligible=complete, policy=policy,
        assessed_at=now, source_evidence=sources,
        session_active=None if state is State.UNKNOWN else state is State.ACTIVE,
        session_context=session_context, session_state=state,
        action_applicability=applicability, session_reasons=session_reasons,
    )
