"""One injected Tonight evaluation and atomic alert claim; no scheduler or delivery."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from decision.models.opportunity_alert import OpportunityAlert, OpportunityAlertPolicy, OpportunityAlertStatus, aware
from decision.services.opportunity_alert_service import OpportunityAlertService
from decision.services.tonight_application_service import TonightResult, TonightStatus


def _utc(value):
    if not aware(value):
        raise ValueError('runner_aware_time_required')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class OpportunityAlertCadence:
    interval: timedelta

    def __post_init__(self):
        if not isinstance(self.interval, timedelta) or self.interval <= timedelta(0):
            raise ValueError('runner_positive_interval_required')

    def next_due(self, last_cycle_time: datetime) -> datetime:
        return _utc(last_cycle_time) + self.interval

    def is_due(self, logical_time: datetime, last_cycle_time: datetime | None) -> bool:
        current = _utc(logical_time)
        return last_cycle_time is None or current >= self.next_due(last_cycle_time)


class OpportunityAlertCycleStatus(str, Enum):
    ALERT_EMITTED = 'ALERT_EMITTED'
    NO_ALERT = 'NO_ALERT'
    ERROR = 'ERROR'


@dataclass(frozen=True, slots=True)
class OpportunityAlertCycleResult:
    status: OpportunityAlertCycleStatus
    evaluated: bool
    logical_time: datetime | None
    reason_codes: tuple[str, ...]
    tonight_status: TonightStatus | None = None
    alert: OpportunityAlert | None = None

    def __post_init__(self):
        if not isinstance(self.status, OpportunityAlertCycleStatus):
            raise TypeError('runner_status_required')
        if (self.status is OpportunityAlertCycleStatus.ALERT_EMITTED) != (self.alert is not None):
            raise ValueError('runner_alert_outcome_mismatch')


class OpportunityAlertRunner:
    """Bind to one user/context and its existing ledger. Caller owns cadence."""
    def __init__(self, *, tonight_service, ledger):
        self.tonight_service = tonight_service
        self.alert_service = OpportunityAlertService(ledger)

    def run_cycle(self, *, policy: OpportunityAlertPolicy, logical_time, **tonight_inputs):
        Status = OpportunityAlertCycleStatus
        try:
            at = _utc(logical_time)
        except (ValueError, TypeError, OverflowError):
            return OpportunityAlertCycleResult(Status.ERROR, False, None, ('invalid_logical_time',))
        if not isinstance(policy, OpportunityAlertPolicy):
            return OpportunityAlertCycleResult(Status.ERROR, False, at, ('invalid_alert_policy',))
        if not policy.enabled:
            return OpportunityAlertCycleResult(Status.NO_ALERT, False, at, ('alerts_disabled',))
        if 'reference_time_utc' in tonight_inputs:
            return OpportunityAlertCycleResult(Status.ERROR, False, at, ('runner_time_override_forbidden',))
        try:
            result = self.tonight_service.evaluate(reference_time_utc=at, **tonight_inputs)
            if not isinstance(result, TonightResult) or not isinstance(result.status, TonightStatus):
                raise TypeError('invalid_tonight_result')
        except Exception:
            return OpportunityAlertCycleResult(Status.ERROR, False, at, ('tonight_evaluation_failed',))
        if result.status is TonightStatus.FORECAST_UNAVAILABLE:
            return OpportunityAlertCycleResult(Status.ERROR, True, at,
                ('tonight_forecast_unavailable',), result.status)
        try:
            decision = self.alert_service.evaluate(result=result, policy=policy, logical_time=at)
        except Exception:
            return OpportunityAlertCycleResult(Status.ERROR, True, at,
                ('opportunity_alert_claim_failed',), result.status)
        status = Status.ALERT_EMITTED if decision.status is OpportunityAlertStatus.ALERT else Status.NO_ALERT
        return OpportunityAlertCycleResult(status, True, at, decision.reason_codes, result.status, decision.alert)
