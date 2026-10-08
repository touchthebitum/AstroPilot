"""Internal v1 alert contract; no notification or persisted replay authority."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from decision.validation.productive_window_evidence import valid_number


class OpportunityAlertStatus(str, Enum):
    NO_ALERT = "NO_ALERT"
    ALERT = "ALERT"


def aware(value):
    return isinstance(value, datetime) and value.utcoffset() is not None


@dataclass(frozen=True, slots=True)
class OpportunityAlertPolicy:
    schema_version: int = 1
    enabled: bool = False
    site_name: str | None = None
    project_keys: tuple[str, ...] = ()
    intent_ids: tuple[str, ...] = ()
    filter_profile_ids: tuple[str, ...] = ()
    min_expected_gain: float = 0
    min_duration_minutes: float = 60
    min_quality: float = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    cooldown_minutes: float = 1440

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported_alert_policy_schema")
        if type(self.enabled) is not bool:
            raise TypeError("alert_policy_enabled_must_be_boolean")
        for name in ("project_keys", "intent_ids", "filter_profile_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"invalid_{name}")
            if self.enabled and not values:
                raise ValueError(f"required_{name}")
        if self.enabled and (not isinstance(self.site_name, str) or not self.site_name.strip()):
            raise ValueError("alert_site_required")
        for name, minimum, maximum in (("min_expected_gain", 0, None),
                ("min_duration_minutes", 60, None), ("min_quality", 0, 100)):
            if not valid_number(getattr(self, name), minimum, maximum):
                raise ValueError(f"invalid_{name}")
        if not valid_number(self.cooldown_minutes, positive=True):
            raise ValueError("invalid_cooldown_minutes")
        for value in (self.window_start, self.window_end):
            if value is not None and not aware(value):
                raise ValueError("alert_policy_aware_time_required")
        if self.window_start and self.window_end and self.window_end.astimezone(timezone.utc) <= self.window_start.astimezone(timezone.utc):
            raise ValueError("alert_policy_window_not_forward")


@dataclass(frozen=True, slots=True)
class OpportunityAlert:
    idempotency_key: str
    project_key: str
    imaging_field_id: str
    acquisition_intent_id: str
    site_name: str
    filter_profile_id: str
    window_start: datetime
    window_end: datetime
    duration_minutes: float
    expected_gain: float
    quality: float
    mission_id: str
    decision_id: str
    selection_id: str
    logical_time: datetime
    schema_version: int = 1
    kind: str = "session_opportunity"


@dataclass(frozen=True, slots=True)
class OpportunityAlertDecision:
    status: OpportunityAlertStatus
    reason_codes: tuple[str, ...]
    alert: OpportunityAlert | None = None

    def __post_init__(self):
        if not isinstance(self.status, OpportunityAlertStatus):
            raise TypeError("alert_status_required")
        if (self.status is OpportunityAlertStatus.ALERT) != (self.alert is not None):
            raise ValueError("alert_decision_outcome_mismatch")
