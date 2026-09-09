from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.mission_input import MissionInput
from decision.mission.night_mission import NightMission
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.recommendation.recommendation import Recommendation
from decision.services.user_selection_mission import UserSelectionMissionService
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
    UserSelectionValidationError,
)


START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
END = datetime(2026, 9, 11, 2, tzinfo=timezone.utc)


class RecordingMissionService:
    def __init__(self):
        self.calls = []

    def create(self, *, winner, objects, recommended_key, build_mission_input):
        mission_input = build_mission_input(
            winner["object_evaluations"][recommended_key]
        )
        self.calls.append(
            {
                "winner": winner,
                "objects": objects,
                "recommended_key": recommended_key,
                "mission_input": mission_input,
            }
        )
        return NightMission(
            target=recommended_key,
            confidence="HIGH",
            equipment=["widefield_setup"],
            site_name="Mont Sujet",
            mission_id=mission_input.mission_id,
            decision_id=mission_input.decision_id,
            selection_id=mission_input.selection_id,
            window_start=mission_input.window_start,
            window_end=mission_input.window_end,
            recommended_hours=mission_input.recommended_hours,
            expected_gain=mission_input.expected_gain,
        )


def recommendation():
    return Recommendation(
        opportunity=SimpleNamespace(
            candidate=SimpleNamespace(catalog_key="M31")
        ),
        confidence=0.9,
    )


def decision_context(*, decision_id="decision-1", evaluated=None):
    return UserSelectionDecisionContext(
        decision_id=decision_id,
        primary_catalog_key="M31",
        exposed_alternative_catalog_keys=("M42",),
        explicitly_evaluated_catalog_keys=(
            tuple(evaluated)
            if evaluated is not None
            else ("M31", "M42", "NGC7000")
        ),
    )


def user_selection(source, catalog_key, *, decision_id="decision-1"):
    return UserSelection(
        selection_id="selection-1",
        decision_id=decision_id,
        selected_catalog_key=catalog_key,
        source=source,
        selected_at=datetime(2026, 9, 9, 20, tzinfo=timezone.utc),
    )


def night():
    evaluations = {
        key: {
            "decision_context": SimpleNamespace(
                site=SimpleNamespace(name="Mont Sujet")
            )
        }
        for key in ("M31", "M42", "NGC7000")
    }
    return {
        "top_objects": [{"catalog_key": key} for key in evaluations],
        "object_evaluations": evaluations,
    }


def mission_input():
    return MissionInput(
        window_start=START,
        window_end=END,
        astronomical_hours=4.0,
        weather=None,
        moon_penalty=None,
        recommended_hours=3.0,
        expected_gain=1.2,
    )


def service(base_input=None):
    mission_service = RecordingMissionService()
    base_input = base_input or mission_input()
    return (
        UserSelectionMissionService(
            tonight_mission_service=mission_service,
            build_mission_input=lambda evaluation, *, profile: base_input,
        ),
        mission_service,
        base_input,
    )


@pytest.mark.parametrize(
    ("source", "catalog_key"),
    [
        (UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        (UserSelectionSource.ALTERNATIVE, "M42"),
        (UserSelectionSource.OTHER_EVALUATED_TARGET, "NGC7000"),
    ],
)
def test_validated_selection_creates_mission_for_selected_target(
    source,
    catalog_key,
):
    composer, mission_service, _ = service()

    mission = composer.create(
        mission_id="mission-1",
        selection=user_selection(source, catalog_key),
        decision_context=decision_context(),
        recommendation=recommendation(),
        night=night(),
        profile={},
    )

    assert mission.target == catalog_key
    assert mission_service.calls[0]["recommended_key"] == catalog_key
    assert mission.decision_id == "decision-1"
    assert mission.selection_id == "selection-1"


def test_other_target_requires_v1_39_validation_before_mission_creation():
    composer, mission_service, _ = service()

    with pytest.raises(
        UserSelectionValidationError,
        match="selected_target_not_explicitly_evaluated",
    ):
        composer.create(
            mission_id="mission-1",
            selection=user_selection(
                UserSelectionSource.OTHER_EVALUATED_TARGET,
                "NGC7000",
            ),
            decision_context=decision_context(evaluated=("M31", "M42")),
            recommendation=recommendation(),
            night=night(),
            profile={},
        )

    assert mission_service.calls == []


def test_declined_selection_creates_no_mission():
    composer, mission_service, _ = service()

    mission = composer.create(
        mission_id="mission-1",
        selection=user_selection(UserSelectionSource.DECLINED, None),
        decision_context=decision_context(),
        recommendation=recommendation(),
        night=night(),
        profile={},
    )

    assert mission is None
    assert mission_service.calls == []


def test_unbound_selection_fails_closed_without_primary_fallback():
    composer, mission_service, _ = service()

    with pytest.raises(
        UserSelectionValidationError,
        match="user_selection_decision_mismatch",
    ):
        composer.create(
            mission_id="mission-1",
            selection=user_selection(
                UserSelectionSource.ALTERNATIVE,
                "M42",
                decision_id="decision-2",
            ),
            decision_context=decision_context(decision_id="decision-1"),
            recommendation=recommendation(),
            night=night(),
            profile={},
        )

    assert mission_service.calls == []


def test_inconsistent_recommendation_context_fails_closed():
    composer, mission_service, _ = service()
    inconsistent_recommendation = Recommendation(
        opportunity=SimpleNamespace(
            candidate=SimpleNamespace(catalog_key="M101")
        ),
        confidence=0.9,
    )

    with pytest.raises(
        UserSelectionValidationError,
        match="recommendation_decision_context_mismatch",
    ):
        composer.create(
            mission_id="mission-1",
            selection=user_selection(UserSelectionSource.ALTERNATIVE, "M42"),
            decision_context=decision_context(),
            recommendation=inconsistent_recommendation,
            night=night(),
            profile={},
        )

    assert mission_service.calls == []


def test_selection_preserves_recommendation_and_source_collections():
    original_recommendation = recommendation()
    original_opportunity = original_recommendation.opportunity
    context = decision_context()
    alternatives = context.exposed_alternative_catalog_keys
    evaluated = context.explicitly_evaluated_catalog_keys
    composer, _, _ = service()

    composer.create(
        mission_id="mission-1",
        selection=user_selection(UserSelectionSource.ALTERNATIVE, "M42"),
        decision_context=context,
        recommendation=original_recommendation,
        night=night(),
        profile={},
    )

    assert original_recommendation.opportunity is original_opportunity
    assert original_recommendation.opportunity.candidate.catalog_key == "M31"
    assert context.exposed_alternative_catalog_keys is alternatives
    assert context.explicitly_evaluated_catalog_keys is evaluated


def test_session_availability_transport_and_constrained_window_are_preserved():
    availability = SessionAvailability(
        SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=2),
    )
    constrained_input = MissionInput(
        window_start=datetime(2026, 9, 10, 23, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 11, 1, tzinfo=timezone.utc),
        astronomical_hours=4.0,
        weather=None,
        moon_penalty=None,
        recommended_hours=2.0,
        expected_gain=0.8,
    )
    composer, mission_service, _ = service(constrained_input)

    mission = composer.create(
        mission_id="mission-1",
        selection=user_selection(UserSelectionSource.ALTERNATIVE, "M42"),
        decision_context=decision_context(),
        recommendation=recommendation(),
        night=night(),
        profile={},
        availability=availability,
    )

    assert mission_service.calls[0]["mission_input"].availability is availability
    assert mission.window_start == constrained_input.window_start
    assert mission.window_end == constrained_input.window_end


def test_omitted_availability_adds_no_temporal_default():
    composer, mission_service, base_input = service()

    composer.create(
        mission_id="mission-1",
        selection=user_selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
        ),
        decision_context=decision_context(),
        recommendation=recommendation(),
        night=night(),
        profile={},
    )

    transported = mission_service.calls[0]["mission_input"]
    assert transported.availability is None
    assert transported.window_start is base_input.window_start
    assert transported.window_end is base_input.window_end
    assert transported.mission_id == "mission-1"
    assert transported.decision_id == "decision-1"
    assert transported.selection_id == "selection-1"


def test_mission_input_rejects_partial_provenance():
    with pytest.raises(ValueError, match="mission_provenance_required"):
        MissionInput(
            window_start=START,
            window_end=END,
            astronomical_hours=4.0,
            weather=None,
            moon_penalty=None,
            recommended_hours=3.0,
            expected_gain=1.2,
            mission_id="mission-1",
        )


def test_created_mission_requires_explicit_mission_id():
    composer, mission_service, _ = service()

    with pytest.raises(TypeError, match="mission_id"):
        composer.create(
            selection=user_selection(
                UserSelectionSource.PRIMARY_RECOMMENDATION,
                "M31",
            ),
            decision_context=decision_context(),
            recommendation=recommendation(),
            night=night(),
            profile={},
        )

    assert mission_service.calls == []


@pytest.mark.parametrize("mission_id", ["", "   ", None])
def test_created_mission_rejects_empty_mission_id(mission_id):
    composer, _, _ = service()

    with pytest.raises(ValueError, match="mission_id_required"):
        composer.create(
            mission_id=mission_id,
            selection=user_selection(
                UserSelectionSource.PRIMARY_RECOMMENDATION,
                "M31",
            ),
            decision_context=decision_context(),
            recommendation=recommendation(),
            night=night(),
            profile={},
        )


@pytest.mark.parametrize(
    ("mission_id", "decision_id", "selection_id"),
    [
        (None, "decision-1", "selection-1"),
        ("mission-1", None, "selection-1"),
        ("mission-1", "decision-1", None),
        ("", "decision-1", "selection-1"),
        ("mission-1", "", "selection-1"),
        ("mission-1", "decision-1", ""),
    ],
)
def test_mission_rejects_partial_or_empty_provenance(
    mission_id,
    decision_id,
    selection_id,
):
    with pytest.raises(ValueError, match="mission_provenance_required"):
        NightMission(
            target="M31",
            confidence="HIGH",
            equipment=["widefield_setup"],
            site_name="Mont Sujet",
            mission_id=mission_id,
            decision_id=decision_id,
            selection_id=selection_id,
        )


def test_mission_contract_is_immutable_and_preserves_stable_identities():
    composer, _, _ = service()
    proposed_selection = user_selection(
        UserSelectionSource.ALTERNATIVE,
        "M42",
    )

    mission = composer.create(
        mission_id="mission-1",
        selection=proposed_selection,
        decision_context=decision_context(),
        recommendation=recommendation(),
        night=night(),
        profile={},
    )

    assert mission.target == "M42"
    assert mission.equipment == ["widefield_setup"]
    assert mission.site_name == "Mont Sujet"
    with pytest.raises(FrozenInstanceError):
        mission.target = "M31"
    with pytest.raises(TypeError, match="immutable_mission_collection"):
        mission.equipment.append("another_setup")
    with pytest.raises(FrozenInstanceError):
        proposed_selection.selected_catalog_key = "M31"


def test_mission_window_is_planned_and_contains_no_execution_semantics():
    contract_fields = {field.name for field in fields(NightMission)}
    forbidden_fields = {
        "actual_window_start",
        "actual_window_end",
        "actual_duration",
        "usable_integration",
        "execution_outcome",
        "execution_status",
        "status",
        "created_at",
    }
    composer, _, _ = service()

    mission = composer.create(
        mission_id="mission-1",
        selection=user_selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
        ),
        decision_context=decision_context(),
        recommendation=recommendation(),
        night=night(),
        profile={},
    )

    assert mission.window_start is START
    assert mission.window_end is END
    assert contract_fields.isdisjoint(forbidden_fields)
