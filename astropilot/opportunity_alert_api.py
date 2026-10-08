"""Allowlisted HTTP transport of the internal alert decision; no business evaluation."""
from datetime import timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict

from astropilot.opportunity_alert_ledger import OpportunityAlertLedgerError
from decision.services.opportunity_alert_service import OpportunityAlertService


class PublicOpportunityAlert(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    alert_id: str
    project_key: str
    imaging_field_id: str
    acquisition_intent_id: str
    site: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    duration_minutes: float
    expected_gain: float
    decision_score: float
    logical_time: AwareDatetime


class OpportunityAlertResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    status: Literal['alert', 'no_alert']
    reason_codes: tuple[str, ...]
    schema_version: Literal[1] = 1
    policy_version: Literal[1] = 1
    alert: PublicOpportunityAlert | None = None


def claim_opportunity_alert(*, result, policy, ledger, logical_time):
    try:
        decision = OpportunityAlertService(ledger).evaluate(
            result=result, policy=policy, logical_time=logical_time)
    except OpportunityAlertLedgerError as error:
        raise HTTPException(status_code=503,
            detail={'code': 'opportunity_alert_ledger_unavailable'}) from error
    alert = decision.alert
    public = None if alert is None else PublicOpportunityAlert(
        alert_id=alert.idempotency_key, project_key=alert.project_key,
        imaging_field_id=alert.imaging_field_id,
        acquisition_intent_id=alert.acquisition_intent_id, site=alert.site_name,
        window_start=alert.window_start.astimezone(timezone.utc),
        window_end=alert.window_end.astimezone(timezone.utc),
        duration_minutes=alert.duration_minutes, expected_gain=alert.expected_gain,
        decision_score=alert.quality, logical_time=alert.logical_time.astimezone(timezone.utc))
    return OpportunityAlertResponse(status=decision.status.value.lower(),
        reason_codes=decision.reason_codes, alert=public)
