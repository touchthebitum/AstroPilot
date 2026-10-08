"""Internal creation authority; persistence and physical assessments never issue it.

Python objects are not a security sandbox. This capability prevents accidental
promotion of raw/replayed inputs and is revalidated at the creation boundary.
"""
from dataclasses import dataclass
from math import isfinite

from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress
from decision.models.session_availability import SessionAvailability
from decision.services.project_decision_provenance import ProjectDecisionProvenance, resolve_project_decision_provenance
from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
from decision.definitions.production_setup_filter_capabilities import build_production_setup_filter_capabilities_resolver
from decision.definitions.production_filter_optical_profiles import build_production_filter_optical_profile_resolver
from decision.services.acquisition_intent_filter_profile_resolution import resolve_acquisition_intent_filter_profile
from decision.models.acquisition_intent_filter_profile_resolution import AcquisitionIntentFilterProfileResolutionStatus

_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ModernMissionAuthorization:
    imaging_field_id: str
    acquisition_intent_id: str
    acquisition_capacity: AcquisitionIntentRemainingProgress
    filter_profile_id: str

    def __init__(self, *, _issuer=None, imaging_field_id, acquisition_intent_id,
                 acquisition_capacity, filter_profile_id):
        if _issuer is not _ISSUER:
            raise TypeError("modern_mission_authorization_requires_internal_factory")
        for key, value in (("imaging_field_id", imaging_field_id),
                           ("acquisition_intent_id", acquisition_intent_id),
                           ("acquisition_capacity", acquisition_capacity),
                           ("filter_profile_id", filter_profile_id)):
            object.__setattr__(self, key, value)


def _issue_from_project(mission_input, *, profile, catalog_key):
    """Called only by the modern input factory after deriving project capacity."""
    project = profile.get("projects", {}).get(catalog_key, {})
    active_equipment = profile.get("active_equipment")
    resolver = build_production_imaging_field_resolver()
    if mission_input.evidence_only or resolve_project_decision_provenance(project, resolver) is not ProjectDecisionProvenance.MODERN_AUTHORIZED:
        return None
    if project.get("imaging_field_id") != mission_input.imaging_field_id:
        return None
    capacity = mission_input.acquisition_capacity
    if not _capacity_valid(capacity, mission_input.acquisition_intent_id):
        return None
    try:
        field = resolver.resolve(mission_input.imaging_field_id)
        intent = next(i for i in field.acquisition_intents if i.acquisition_intent_id == mission_input.acquisition_intent_id)
        from decision.services.project_acquisition_intent_targets import resolve_project_acquisition_intent_targets
        from decision.services.project_acquisition_intent_progress import resolve_project_acquisition_intent_progress
        from decision.services.acquisition_intent_remaining_progress import derive_acquisition_intent_remaining_progress
        from decision.services.intent_progress_credit import credit_totals
        derived = derive_acquisition_intent_remaining_progress(
            field, resolve_project_acquisition_intent_targets(project, resolver),
            resolve_project_acquisition_intent_progress(project, resolver),
            credit_totals(profile, catalog_key),
        )
        if capacity != next((item for item in derived if item.acquisition_intent_id == intent.acquisition_intent_id), None):
            return None
        capabilities = build_production_setup_filter_capabilities_resolver().resolve(active_equipment)
        resolution = resolve_acquisition_intent_filter_profile(intent, capabilities, build_production_filter_optical_profile_resolver())
    except (ValueError, TypeError, StopIteration):
        return None
    if resolution.status is not AcquisitionIntentFilterProfileResolutionStatus.RESOLVED:
        return None
    return ModernMissionAuthorization(_issuer=_ISSUER,
        imaging_field_id=field.imaging_field_id,
        acquisition_intent_id=intent.acquisition_intent_id,
        acquisition_capacity=capacity,
        filter_profile_id=resolution.matching_filter_profile_ids[0])


def _capacity_valid(capacity, intent_id):
    return (isinstance(capacity, AcquisitionIntentRemainingProgress)
            and capacity.acquisition_intent_id == intent_id
            and isinstance(capacity.remaining_hours, (int, float))
            and not isinstance(capacity.remaining_hours, bool)
            and isfinite(capacity.remaining_hours)
            and capacity.remaining_hours >= 1
            and not capacity.completed)


def authorization_refusal(value):
    if value is None:
        return "modern_mission_input_required"
    if value.evidence_only:
        return "preselection_evidence_cannot_authorize_mission"
    authority = value.creation_authorization
    if type(authority) is not ModernMissionAuthorization:
        return "modern_mission_authorization_required"
    if (value.imaging_field_id != authority.imaging_field_id
            or value.acquisition_intent_id != authority.acquisition_intent_id
            or value.acquisition_capacity != authority.acquisition_capacity):
        return "modern_mission_authorization_mismatch"
    if not _capacity_valid(value.acquisition_capacity, value.acquisition_intent_id):
        return "modern_mission_capacity_insufficient"
    if not isinstance(value.availability, SessionAvailability):
        return "user_availability_required"
    if value.selected_filter is not None:
        return "legacy_filter_cannot_authorize_modern_mission"
    return None
