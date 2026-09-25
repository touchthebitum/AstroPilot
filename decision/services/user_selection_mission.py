from collections.abc import Mapping
from dataclasses import replace

from decision.mission.night_mission import NightMission
from decision.filtering.intent_filter_reconciliation import (
    validate_selected_filter_for_intent,
)
from decision.models.session_availability import SessionAvailability
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.recommendation.recommendation import Recommendation
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
    UserSelectionValidationError,
    validate_user_selection,
)


def _candidate_catalog_key(candidate) -> str | None:
    catalog_key = getattr(candidate, "catalog_key", None)
    if catalog_key is None and hasattr(candidate, "get"):
        catalog_key = candidate.get("catalog_key")
    return catalog_key


def _selected_candidate(recommendation, selected_catalog_key):
    opportunity = recommendation.opportunity
    primary = getattr(opportunity, "candidate", None)
    if _candidate_catalog_key(primary) == selected_catalog_key:
        return primary
    matches = [
        candidate
        for candidate in getattr(opportunity, "shortlist_entries", ())
        if _candidate_catalog_key(candidate) == selected_catalog_key
    ]
    return matches[0] if len(matches) == 1 else None


class UserSelectionMissionService:
    def __init__(self, *, tonight_mission_service, build_mission_input):
        self.tonight_mission_service = tonight_mission_service
        self.build_mission_input = build_mission_input

    def create(
        self,
        *,
        mission_id: str,
        selection: UserSelection,
        decision_context: UserSelectionDecisionContext,
        recommendation: Recommendation,
        night: Mapping,
        profile: Mapping,
        availability: SessionAvailability | None = None,
    ) -> NightMission | None:
        if not isinstance(mission_id, str) or not mission_id.strip():
            raise ValueError("mission_id_required")
        validated_selection = validate_user_selection(
            selection,
            decision_context,
        )
        if validated_selection.source is UserSelectionSource.DECLINED:
            return None

        if not isinstance(recommendation, Recommendation):
            raise TypeError("Expected Recommendation")
        primary_catalog_key = _candidate_catalog_key(
            recommendation.opportunity.candidate
        )
        if (
            decision_context.primary_catalog_key is not None
            and primary_catalog_key != decision_context.primary_catalog_key
        ):
            raise UserSelectionValidationError(
                "recommendation_decision_context_mismatch"
            )

        selected_candidate = _selected_candidate(
            recommendation,
            validated_selection.selected_catalog_key,
        )
        if (
            validated_selection.selected_imaging_field_id is not None
            and validated_selection.selected_acquisition_intent_id is None
            and getattr(
                selected_candidate,
                "acquisition_intent_selection_status",
                None,
            )
            is not None
        ):
            raise UserSelectionValidationError(
                "acquisition_intent_required_for_mission"
            )

        selected_catalog_key = validated_selection.selected_catalog_key
        object_evaluations = night.get("object_evaluations")
        if (
            not isinstance(object_evaluations, Mapping)
            or selected_catalog_key not in object_evaluations
        ):
            raise UserSelectionValidationError(
                "selected_target_evaluation_unavailable"
            )
        selected_object = next(
            (
                item
                for item in (night.get("top_objects") or ())
                if _candidate_catalog_key(item) == selected_catalog_key
            ),
            None,
        )
        if not isinstance(selected_object, Mapping):
            raise UserSelectionValidationError(
                "selected_target_evaluation_unavailable"
            )

        def build_selected_mission_input(evaluation):
            evaluation = {
                **evaluation,
                "imaging_field_id": (
                    validated_selection.selected_imaging_field_id
                ),
                "selected_acquisition_intent_id": (
                    validated_selection.selected_acquisition_intent_id
                ),
            }
            mission_input = self.build_mission_input(
                evaluation,
                profile=profile,
            )
            return replace(
                mission_input,
                availability=availability,
                mission_id=mission_id,
                decision_id=validated_selection.decision_id,
                selection_id=validated_selection.selection_id,
                imaging_field_id=(
                    validated_selection.selected_imaging_field_id
                ),
                acquisition_intent_id=(
                    validated_selection.selected_acquisition_intent_id
                ),
            )

        mission = self.tonight_mission_service.create(
            winner=night,
            objects=night.get("top_objects") or [],
            recommended_key=selected_catalog_key,
            build_mission_input=build_selected_mission_input,
        )
        if mission is None:
            raise UserSelectionValidationError("selected_target_not_actionable")
        if not isinstance(mission, NightMission):
            raise TypeError("Expected NightMission or None")
        validate_selected_filter_for_intent(
            imaging_field_id=mission.imaging_field_id,
            acquisition_intent_id=mission.acquisition_intent_id,
            selected_filter=mission.selected_filter,
        )
        expected_mission_targets = {
            selected_catalog_key,
            selected_object.get("name"),
        }
        if mission.target not in expected_mission_targets:
            raise UserSelectionValidationError("mission_target_mismatch")

        selected_evaluation = object_evaluations[selected_catalog_key]
        decision_context_value = (
            selected_evaluation.get("decision_context")
            if isinstance(selected_evaluation, Mapping)
            else None
        )
        site = getattr(decision_context_value, "site", None)
        site_name = getattr(site, "name", None)
        if (
            not isinstance(site_name, str)
            or not site_name.strip()
            or mission.site_name != site_name
        ):
            raise UserSelectionValidationError("mission_site_identity_mismatch")
        if (
            mission.mission_id != mission_id
            or mission.decision_id != validated_selection.decision_id
            or mission.selection_id != validated_selection.selection_id
        ):
            raise UserSelectionValidationError("mission_provenance_mismatch")
        if (
            mission.imaging_field_id
            != validated_selection.selected_imaging_field_id
        ):
            raise UserSelectionValidationError(
                "mission_imaging_field_mismatch"
            )
        if (
            mission.acquisition_intent_id
            != validated_selection.selected_acquisition_intent_id
        ):
            raise UserSelectionValidationError(
                "mission_acquisition_intent_mismatch"
            )
        return mission
