from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from decision.mission.night_mission import NightMission
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceApplicationService,
    DecisionAcceptanceError,
    InMemoryDecisionAcceptanceContextStore,
)
from decision.services.user_selection_validator import UserSelectionDecisionContext


SELECTED_AT = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)


class RecordingSelectionMissionService:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        selection = kwargs["selection"]
        if selection.source is UserSelectionSource.DECLINED:
            return None
        return NightMission(
            target=selection.selected_catalog_key,
            confidence="HIGH",
            equipment=["setup"],
            site_name="Mont Sujet",
            mission_id=kwargs["mission_id"],
            decision_id=selection.decision_id,
            selection_id=selection.selection_id,
        )


def selection(source, target, *, decision_id="decision-1"):
    return UserSelection(
        selection_id="selection-1",
        decision_id=decision_id,
        selected_catalog_key=target,
        source=source,
        selected_at=SELECTED_AT,
    )


def registered_service():
    composer = RecordingSelectionMissionService()
    store = InMemoryDecisionAcceptanceContextStore()
    service = DecisionAcceptanceApplicationService(
        selection_mission_service=composer,
        context_store=store,
        mission_id_factory=lambda: "mission-1",
    )
    recommendation = SimpleNamespace(
        opportunity=SimpleNamespace(
            candidate=SimpleNamespace(catalog_key="M31")
        )
    )
    night = {"object_evaluations": {key: {} for key in ("M31", "M42", "M33")}}
    service.register_decision(
        decision_id="decision-1",
        recommendation=recommendation,
        night=night,
        profile={"active_equipment": "setup"},
        availability=None,
        primary_catalog_key="M31",
        exposed_alternative_catalog_keys=("M42",),
        explicitly_evaluated_catalog_keys=("M31", "M42", "M33"),
    )
    return service, composer, store, recommendation


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        (UserSelectionSource.ALTERNATIVE, "M42"),
        (UserSelectionSource.OTHER_EVALUATED_TARGET, "M33"),
    ],
)
def test_exact_registered_decision_creates_provenance_bound_mission(source, target):
    service, composer, _, _ = registered_service()

    mission = service.accept(selection(source, target))

    assert mission.target == target
    assert (
        mission.mission_id,
        mission.decision_id,
        mission.selection_id,
    ) == ("mission-1", "decision-1", "selection-1")
    assert composer.calls[0]["decision_context"] == UserSelectionDecisionContext(
        decision_id="decision-1",
        primary_catalog_key="M31",
        exposed_alternative_catalog_keys=("M42",),
        explicitly_evaluated_catalog_keys=("M31", "M42", "M33"),
    )


def test_declined_selection_resolves_exact_decision_and_creates_no_mission():
    service, composer, _, _ = registered_service()

    assert service.accept(selection(UserSelectionSource.DECLINED, None)) is None
    assert len(composer.calls) == 1


def test_unknown_decision_does_not_fall_back_to_latest_or_reevaluate():
    service, composer, _, _ = registered_service()

    with pytest.raises(DecisionAcceptanceError, match="decision_context_not_found"):
        service.accept(
            selection(
                UserSelectionSource.PRIMARY_RECOMMENDATION,
                "M31",
                decision_id="unknown-decision",
            )
        )

    assert composer.calls == []


def test_mismatched_loaded_context_fails_closed():
    class MismatchedStore:
        def load(self, *, decision_id):
            return SimpleNamespace(
                decision_context=UserSelectionDecisionContext(
                    decision_id="another-decision",
                    primary_catalog_key="M31",
                    exposed_alternative_catalog_keys=(),
                    explicitly_evaluated_catalog_keys=("M31",),
                )
            )

    composer = RecordingSelectionMissionService()
    service = DecisionAcceptanceApplicationService(
        selection_mission_service=composer,
        context_store=MismatchedStore(),
        mission_id_factory=lambda: "mission-1",
    )

    with pytest.raises(DecisionAcceptanceError, match="decision_context_mismatch"):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))
    assert composer.calls == []


def test_incomplete_decision_context_fails_closed():
    class IncompleteStore:
        def load(self, *, decision_id):
            return SimpleNamespace(decision_context=None)

    service = DecisionAcceptanceApplicationService(
        selection_mission_service=RecordingSelectionMissionService(),
        context_store=IncompleteStore(),
        mission_id_factory=lambda: "mission-1",
    )

    with pytest.raises(DecisionAcceptanceError, match="decision_context_incomplete"):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))


def test_registration_snapshots_source_context_without_mutating_recommendation():
    service, _, store, recommendation = registered_service()
    original_primary = recommendation.opportunity.candidate.catalog_key

    stored = store.load(decision_id="decision-1")

    assert stored.recommendation is not recommendation
    assert stored.decision_context.primary_catalog_key == original_primary
    assert recommendation.opportunity.candidate.catalog_key == "M31"
