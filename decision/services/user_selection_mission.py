from collections.abc import Mapping
from dataclasses import replace

from decision.mission.night_mission import NightMission
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


class UserSelectionMissionService:
    def __init__(self, *, tonight_mission_service, build_mission_input):
        self.tonight_mission_service = tonight_mission_service
        self.build_mission_input = build_mission_input

    def create(
        self,
        *,
        selection: UserSelection,
        decision_context: UserSelectionDecisionContext,
        recommendation: Recommendation,
        night: Mapping,
        profile: Mapping,
        availability: SessionAvailability | None = None,
    ) -> NightMission | None:
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
        if primary_catalog_key != decision_context.primary_catalog_key:
            raise UserSelectionValidationError(
                "recommendation_decision_context_mismatch"
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

        def build_selected_mission_input(evaluation):
            mission_input = self.build_mission_input(
                evaluation,
                profile=profile,
            )
            if availability is None:
                return mission_input
            return replace(mission_input, availability=availability)

        mission = self.tonight_mission_service.create(
            winner=night,
            objects=night.get("top_objects") or [],
            recommended_key=selected_catalog_key,
            build_mission_input=build_selected_mission_input,
        )
        if mission is None:
            return None
        if not isinstance(mission, NightMission):
            raise TypeError("Expected NightMission or None")
        return replace(
            mission,
            decision_id=validated_selection.decision_id,
            selection_id=validated_selection.selection_id,
        )
