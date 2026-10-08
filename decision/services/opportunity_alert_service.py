"""Conservative consumer of admissible live Tonight outputs, with atomic claims."""
import hashlib
import json
from datetime import timedelta, timezone
from math import ceil
from threading import Lock
from typing import Protocol

from decision.models.opportunity_alert import (
    OpportunityAlert, OpportunityAlertDecision, OpportunityAlertPolicy,
    OpportunityAlertStatus as Status, aware,
)
from decision.models.candidate import CandidateProvenance
from decision.models.acquisition_intent_eligibility import AcquisitionIntentEligibilityStatus
from decision.mission.modern_mission_authorization import authorization_refusal
from decision.services.tonight_application_service import TonightStatus, _ALERT_LIVE_MARKER
from decision.validation.decision_consistency import DecisionConsistencyGate, DecisionConsistencyError
from decision.validation.productive_window_evidence import valid_number, RANGES, SERIES
from decision.models.session_availability import SessionAvailabilityMode
from decision.time_math import elapsed_hours
from decision.weather.provider_reliability import VALUE_RANGES, WeatherVariable


class OpportunityAlertLedger(Protocol):
    """One user per ledger. Durable implementations must claim atomically."""
    def claim(self, *, key, family, logical_time, cooldown_minutes, policy_version=1) -> bool: ...


class InMemoryOpportunityAlertLedger:
    def __init__(self):
        self._lock = Lock()
        self._keys = set()
        self._families = {}
        self._latest_time = None

    def claim(self, *, key, family, logical_time, cooldown_minutes, policy_version=1):
        if type(policy_version) is not int or policy_version != 1:
            raise ValueError("unsupported_alert_ledger_policy")
        with self._lock:
            if self._latest_time is not None and logical_time < self._latest_time:
                return False
            self._latest_time = logical_time
            last = self._families.get(family)
            if key in self._keys or (last is not None and
                    logical_time < last + timedelta(minutes=cooldown_minutes)):
                return False
            self._keys.add(key)
            self._families[family] = logical_time
            return True


def _hash(parts):
    return hashlib.sha256(json.dumps(parts, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _no(reason):
    return OpportunityAlertDecision(Status.NO_ALERT, (reason,))


class OpportunityAlertService:
    def __init__(self, ledger: OpportunityAlertLedger):
        self.ledger = ledger

    def evaluate(self, *, result, policy: OpportunityAlertPolicy, logical_time):
        if not isinstance(policy, OpportunityAlertPolicy):
            raise TypeError("OpportunityAlertPolicy required")
        if not aware(logical_time):
            raise ValueError("alert_logical_time_must_be_aware")
        logical_time = logical_time.astimezone(timezone.utc)
        if not policy.enabled:
            return _no("alerts_disabled")
        if result.alert_live_marker is not _ALERT_LIVE_MARKER:
            return _no("live_tonight_result_required")
        if result.status is not TonightStatus.AVAILABLE or result.actionability_refusal is not None:
            return _no("tonight_not_admissible")
        if result.recommendation is None or result.mission is None:
            return _no("recommendation_and_mission_required")
        if result.forecast_evidence is None or not result.forecast_evidence.forecast_points:
            return _no("forecast_provenance_required")
        value, assessment, mission = result.alert_mission_input, result.alert_assessment, result.mission
        refusal = authorization_refusal(value)
        if refusal:
            return _no(refusal)
        if assessment is None or assessment.evidence_issues:
            return _no("productive_evidence_required")
        if assessment.acquisition_capacity != value.acquisition_capacity:
            return _no("productive_capacity_mismatch")
        # Verify presence/completeness using the existing evidence contract. No
        # weather estimation, productivity evaluation or ranking happens here.
        weather = value.weather
        if weather is None or not valid_number(value.astronomical_hours, positive=True):
            return _no("weather_evidence_required")
        for metric, (minimum, maximum) in RANGES.items():
            series = getattr(weather, SERIES[metric], None)
            if not isinstance(series, (list, tuple)) or len(series) < ceil(value.astronomical_hours) or any(
                    not valid_number(v, minimum, maximum, positive=metric == "seeing") for v in series):
                return _no("weather_evidence_incomplete")
        temperatures = getattr(weather, "hourly_temperature", None)
        bounds = VALUE_RANGES[WeatherVariable.TEMPERATURE_C]
        if (not isinstance(temperatures, (list, tuple))
                or len(temperatures) < ceil(value.astronomical_hours)
                or any(not valid_number(v, *bounds) for v in temperatures)):
            return _no("aqi_temperature_evidence_required")
        candidate = result.recommendation.opportunity.candidate
        authority = value.creation_authorization
        identities = (mission.mission_id, mission.decision_id, mission.selection_id,
            mission.imaging_field_id, mission.acquisition_intent_id, authority.filter_profile_id)
        if any(not isinstance(v, str) or not v.strip() for v in identities):
            return _no("modern_lineage_required")
        if (candidate.provenance is not CandidateProvenance.PROJECT
                or candidate.imaging_field_id != mission.imaging_field_id
                or candidate.selected_acquisition_intent_id != mission.acquisition_intent_id
                or value.imaging_field_id != mission.imaging_field_id
                or value.acquisition_intent_id != mission.acquisition_intent_id
                or (value.mission_id, value.decision_id, value.selection_id) != identities[:3]
                or candidate.lunar_evidence_snapshot != value.lunar_evidence_snapshot
                or mission.lunar_evidence_snapshot != value.lunar_evidence_snapshot):
            return _no("selected_identity_mismatch")
        selected = next((item for item in candidate.acquisition_intent_assessments
            if item.acquisition_intent_id == mission.acquisition_intent_id), None)
        if selected is None or selected.status is not AcquisitionIntentEligibilityStatus.ELIGIBLE:
            return _no("eligible_intent_required")
        if (candidate.catalog_key not in policy.project_keys or mission.site_name != policy.site_name
                or mission.acquisition_intent_id not in policy.intent_ids
                or authority.filter_profile_id not in policy.filter_profile_ids):
            return _no("user_identity_constraints")
        try:
            DecisionConsistencyGate.validate_mission(mission)
        except DecisionConsistencyError:
            return _no("mission_inconsistent")
        start, end = mission.window_start, mission.window_end
        if not all(aware(v) for v in (start, end, result.timeline_start, value.window_start, value.window_end)):
            return _no("window_evidence_required")
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if start < logical_time:
            return _no("session_already_started")
        if (assessment.window_start != value.window_start or assessment.window_end != value.window_end
                or result.timeline_start != value.window_start
                or start < value.window_start.astimezone(timezone.utc)
                or end > value.window_end.astimezone(timezone.utc)
                or mission.productivity != assessment.productivity):
            return _no("productive_evidence_mismatch")
        # Select nothing: require the already selected mission interval to be
        # contained in one of Tonight's existing continuous productive windows.
        anchor = result.timeline_start.astimezone(timezone.utc)
        if not any(anchor + timedelta(hours=w.start_hour) <= start and
                end <= anchor + timedelta(hours=w.end_hour) for w in assessment.productivity.windows):
            return _no("continuous_productive_window_required")
        available = value.availability
        mode = available.mode
        lower = available.start if mode in (SessionAvailabilityMode.FIXED_WINDOW, SessionAvailabilityMode.START_AND_DURATION) else value.window_start
        upper = available.end if mode in (SessionAvailabilityMode.FIXED_WINDOW, SessionAvailabilityMode.UNTIL) else value.window_end
        lower, upper = lower.astimezone(timezone.utc), upper.astimezone(timezone.utc)
        if available.duration is not None:
            upper = min(upper, lower + available.duration)
        if start < lower or end > upper:
            return _no("authorized_availability_mismatch")
        duration = elapsed_hours(start, end) * 60
        if (duration < policy.min_duration_minutes or mission.recommended_hours * 60 < policy.min_duration_minutes
                or not valid_number(mission.expected_gain, positive=True)
                or mission.expected_gain < policy.min_expected_gain
                or mission.recommended_hours > assessment.recommended_hours + .011
                or mission.expected_gain > assessment.expected_gain + .011):
            return _no("gain_or_duration_threshold")
        quality = mission.astro_quality
        if (quality is None or quality.status != "complete" or quality.decision_eligible is not True
                or quality.completeness != 1 or quality.missing_metrics
                or not valid_number(quality.decision_score, 0, 100)):
            return _no("complete_decision_aqi_required")
        if quality.decision_score < policy.min_quality:
            return _no("quality_threshold")
        if ((policy.window_start is not None and start < policy.window_start.astimezone(timezone.utc))
                or (policy.window_end is not None and end > policy.window_end.astimezone(timezone.utc))):
            return _no("user_time_constraints")
        family = [1, candidate.catalog_key, mission.imaging_field_id,
            mission.acquisition_intent_id, mission.site_name, authority.filter_profile_id]
        key = _hash(family + [start.isoformat(), end.isoformat(), mission.decision_id, mission.selection_id])
        if not self.ledger.claim(key=key, family=_hash(family), logical_time=logical_time,
                cooldown_minutes=policy.cooldown_minutes, policy_version=policy.schema_version):
            return _no("duplicate_or_cooldown")
        alert = OpportunityAlert(key, candidate.catalog_key, mission.imaging_field_id,
            mission.acquisition_intent_id, mission.site_name, authority.filter_profile_id,
            start, end, duration, mission.expected_gain, quality.decision_score,
            mission.mission_id, mission.decision_id, mission.selection_id, logical_time)
        return OpportunityAlertDecision(Status.ALERT, ("personalized_conditions_met",), alert)
