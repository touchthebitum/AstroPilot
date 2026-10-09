"""Strict injected-evidence transport; no live observation or execution authority."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictFloat, field_validator
from decision.models.guardian import GuardianEvidence, GuardianObservation, GuardianSessionContext
from decision.runners.guardian_runner import GuardianRunner


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class EvidenceBase(StrictModel):
    source: str = Field(strict=True, min_length=1, max_length=128)
    provenance: Literal['OBSERVATION', 'FORECAST']
    timestamp: AwareDatetime

    @field_validator('source')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('source must be nonblank')
        return value

    @field_validator('timestamp', mode='before')
    @classmethod
    def timestamp_string(cls, value):
        if not isinstance(value, str):
            raise ValueError('timestamp must be an aware ISO string')
        return value

    def domain(self):
        return GuardianEvidence(self.value, self.source, self.provenance, self.timestamp)


class RainEvidence(EvidenceBase):
    value: StrictBool


class NumericEvidence(EvidenceBase):
    value: StrictFloat = Field(allow_inf_nan=False)


class RainEtaEvidence(EvidenceBase):
    value: StrictFloat | None = Field(allow_inf_nan=False)


class Observations(StrictModel):
    rain_active: RainEvidence | None = None
    rain_eta_minutes: RainEtaEvidence | None = None
    wind_kmh: NumericEvidence | None = None
    gust_kmh: NumericEvidence | None = None
    humidity_percent: NumericEvidence | None = None
    dew_spread_c: NumericEvidence | None = None

    def domain(self):
        return GuardianObservation(**{name: None if (e := getattr(self, name)) is None else e.domain()
                                      for name in type(self).model_fields})


class SessionContext(StrictModel):
    session_active: StrictBool
    observed_at: AwareDatetime

    @field_validator('observed_at', mode='before')
    @classmethod
    def timestamp_string(cls, value):
        if not isinstance(value, str):
            raise ValueError('observed_at must be an aware ISO string')
        return value

    def domain(self):
        return GuardianSessionContext(self.session_active, self.observed_at)


class GuardianEvaluateRequest(StrictModel):
    observations: Observations
    session_context: SessionContext | None


CHANNELS = tuple(Observations.model_fields)
REASONS = frozenset(
    [name + ':missing_invalid_untrusted_or_stale' for name in CHANNELS]
    + ['rain_active:CRITICAL', 'rain_eta_minutes:CRITICAL']
    + [name + ':' + level for name in ('wind_kmh', 'gust_kmh', 'humidity_percent', 'dew_spread_c')
       for level in ('WATCH', 'WARNING', 'CRITICAL')]
)
SESSION_REASONS = frozenset('session_context:' + code for code in ('missing', 'invalid', 'future_or_stale'))


class GuardianEvaluateResponse(StrictModel):
    schema_version: Literal['guardian-api-v1'] = 'guardian-api-v1'
    policy_version: str
    risk_level: Literal['SAFE', 'WATCH', 'WARNING', 'CRITICAL', 'UNKNOWN']
    recommended_action: Literal['CONTINUE', 'MONITOR', 'PREPARE_STOP', 'STOP_SESSION', 'EMERGENCY_STOP']
    session_state: Literal['ACTIVE', 'INACTIVE', 'UNKNOWN']
    action_applicability: Literal['APPLICABLE', 'NOT_APPLICABLE', 'UNKNOWN']
    decision_eligible: StrictBool
    evidence_complete: StrictBool
    reasons: tuple[str, ...]
    session_reasons: tuple[str, ...]
    assessed_at: AwareDatetime

    @field_validator('reasons', 'session_reasons')
    @classmethod
    def allowed_reasons(cls, value, info):
        allowed = REASONS if info.field_name == 'reasons' else SESSION_REASONS
        if any(reason not in allowed for reason in value):
            raise ValueError('unsupported reason')
        return value


def evaluate(request: GuardianEvaluateRequest, runner: GuardianRunner, now: datetime) -> GuardianEvaluateResponse:
    result = runner.evaluate(request.observations.domain(), now=now,
        session_context=None if request.session_context is None else request.session_context.domain())
    return GuardianEvaluateResponse(
        policy_version=result.policy.version, risk_level=result.risk_level.name,
        recommended_action=result.action.name, session_state=result.session_state.value,
        action_applicability=result.action_applicability.value,
        decision_eligible=result.decision_eligible, evidence_complete=result.evidence_complete,
        reasons=result.reasons, session_reasons=result.session_reasons,
        assessed_at=result.assessed_at.astimezone(timezone.utc))
