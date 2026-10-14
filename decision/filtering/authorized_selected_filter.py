"""Mission display facts derived only after modern creation authorization."""
from decision.filtering.selected_filter import SelectedFilter
from decision.filtering.intent_filter_reconciliation import resolve_required_filter_type
from decision.definitions.production_filter_optical_profiles import build_production_filter_optical_profile_resolver
from decision.mission.modern_mission_authorization import ModernMissionAuthorization
from decision.validation.decision_consistency import DecisionConsistencyError


def authorized_selected_filter(authority):
    if type(authority) is not ModernMissionAuthorization:
        raise DecisionConsistencyError(['modern_mission_authorization_required'])
    try:
        optical = build_production_filter_optical_profile_resolver().resolve(authority.filter_profile_id)
        required = resolve_required_filter_type(authority.imaging_field_id, authority.acquisition_intent_id)
    except ValueError as exc:
        raise DecisionConsistencyError(['authorized_filter_profile_unresolved']) from exc
    if optical.filter_type != required:
        raise DecisionConsistencyError(['authorized_filter_profile_intent_mismatch'])
    return SelectedFilter(name=f'{optical.filter_type} {optical.fwhm_nm:g} nm',
        filter_type=optical.filter_type, bandwidth_nm=optical.fwhm_nm,
        source='authorized_optical_profile')
