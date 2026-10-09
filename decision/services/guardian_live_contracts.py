"""Pure validation of explicit session and onset-capability contracts."""
from datetime import datetime
import math
from decision.models.guardian import GuardianSessionState as State, GuardianActionApplicability as Applicability
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.models.guardian_rain import GuardianRainUncertainty, GuardianRainInterval, GuardianRainEtaStatus


def fresh(timestamp, now, max_age):
    return (isinstance(timestamp, datetime) and timestamp.utcoffset() is not None
            and 0 <= (now-timestamp).total_seconds() <= max_age)


def live_session(evidence: GuardianLiveSessionEvidence, now: datetime):
    if (evidence.version != 'guardian-live-session-v1'
            or evidence.source != 'caller_session_heartbeat_v1'
            or evidence.provenance != 'CALLER_ASSERTED'
            or not isinstance(evidence.state, State)
            or (evidence.session_id is not None and
                (not isinstance(evidence.session_id, str) or not evidence.session_id.strip()))):
        return State.UNKNOWN, Applicability.UNKNOWN, ('session_context:invalid',)
    if not fresh(evidence.observed_at, now, 900):
        return State.UNKNOWN, Applicability.UNKNOWN, ('session_context:future_or_stale',)
    if evidence.state is State.UNKNOWN:
        return State.UNKNOWN, Applicability.UNKNOWN, ('session_context:unknown',)
    return (evidence.state,
            Applicability.APPLICABLE if evidence.state is State.ACTIVE else Applicability.NOT_APPLICABLE, ())


def _number(value, maximum=None):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0
            and (maximum is None or value <= maximum))


def rain_onset_valid(evidence: GuardianRainUncertainty) -> bool:
    """Ancillary forecasts cannot replace the required trustworthy onset channel."""
    if (evidence.version != 'guardian-rain-uncertainty-v1'
            or evidence.source != 'caller_onset_v1'
            or evidence.eta_status is not GuardianRainEtaStatus.ONSET_CAPABLE
            or not _number(evidence.value)
            or type(evidence.intervals) is not tuple):
        return False
    previous_end = None
    for sample in evidence.intervals:
        if (not isinstance(sample, GuardianRainInterval)
                or not isinstance(sample.start, datetime) or sample.start.utcoffset() is None
                or not isinstance(sample.end, datetime) or sample.end.utcoffset() is None
                or sample.start >= sample.end
                or (previous_end is not None and sample.start < previous_end)
                or (sample.rain_mm is None and sample.probability_percent is None)
                or (sample.rain_mm is not None and not _number(sample.rain_mm))
                or (sample.probability_percent is not None and not _number(sample.probability_percent,100))):
            return False
        previous_end = sample.end
    return True
