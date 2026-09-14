from datetime import datetime, timedelta, timezone
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
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


SELECTED_AT = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
ACCEPTED_AT = datetime(2026, 9, 10, 21, tzinfo=timezone.utc)
SITE = WeatherLocation(46.75, 6.55)
DEFAULT_EVIDENCE = object()


def forecast_evidence(*retrieved_at_values):
    return DecisionForecastEvidence(tuple(
        WeatherForecastPoint(
            provider_id="open_meteo",
            model_id="best_match",
            retrieved_at_utc=retrieved_at,
            forecast_for_utc=ACCEPTED_AT + timedelta(hours=index + 1),
            requested_location=SITE,
            grid_location=SITE,
            values=(WeatherValue(
                WeatherVariable.CLOUD_COVER_PERCENT,
                20.0,
                "%",
            ),),
        )
        for index, retrieved_at in enumerate(retrieved_at_values)
    ))


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


def selection(
    source,
    target,
    *,
    selection_id="selection-1",
    decision_id="decision-1",
    selected_at=SELECTED_AT,
):
    return UserSelection(
        selection_id=selection_id,
        decision_id=decision_id,
        selected_catalog_key=target,
        source=source,
        selected_at=selected_at,
    )


def registered_service(
    *,
    evidence=DEFAULT_EVIDENCE,
    accepted_at=ACCEPTED_AT,
    window_end=None,
):
    if evidence is DEFAULT_EVIDENCE:
        evidence = forecast_evidence(accepted_at - timedelta(minutes=30))
    if window_end is None:
        window_end = accepted_at + timedelta(hours=2)
    composer = RecordingSelectionMissionService()
    store = InMemoryDecisionAcceptanceContextStore()
    service = DecisionAcceptanceApplicationService(
        selection_mission_service=composer,
        context_store=store,
        mission_id_factory=lambda: "mission-1",
        evidence_loader=lambda *, decision_id: evidence,
        clock=lambda: accepted_at,
    )
    recommendation = SimpleNamespace(
        opportunity=SimpleNamespace(
            candidate=SimpleNamespace(catalog_key="M31")
        )
    )
    night = {
        "object_evaluations": {
            key: {
                "decision_context": SimpleNamespace(
                    session=SimpleNamespace(end_time=window_end)
                )
            }
            for key in ("M31", "M42", "M33")
        }
    }
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


def test_first_idempotent_acceptance_and_replay_return_canonical_lineage():
    service, composer, store, recommendation = registered_service()

    first = service.accept_idempotently(
        selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        acceptance_request_id="request-1",
    )
    replay = service.accept_idempotently(
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-retry",
        ),
        acceptance_request_id="request-1",
    )

    assert first == replay
    assert replay.selection.selection_id == "selection-1"
    assert replay.mission.mission_id == "mission-1"
    assert replay.mission.selection_id == replay.selection.selection_id
    assert store.load_acceptance("request-1") == (
        replay.selection,
        replay.mission,
    )
    assert len(composer.calls) == 1
    assert recommendation.opportunity.candidate.catalog_key == "M31"


@pytest.mark.parametrize(
    "conflicting",
    [
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-2",
            decision_id="decision-2",
        ),
        selection(
            UserSelectionSource.ALTERNATIVE,
            "M42",
            selection_id="selection-2",
        ),
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M42",
            selection_id="selection-2",
        ),
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-2",
            selected_at=SELECTED_AT + timedelta(seconds=1),
        ),
    ],
    ids=["decision", "source", "target", "selected-at"],
)
def test_idempotency_key_reuse_with_different_payload_fails_closed(conflicting):
    service, composer, store, _ = registered_service()
    service.accept_idempotently(
        selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        acceptance_request_id="request-1",
    )
    canonical = store.load_acceptance("request-1")

    with pytest.raises(
        DecisionAcceptanceError,
        match="acceptance_request_conflict",
    ):
        service.accept_idempotently(
            conflicting,
            acceptance_request_id="request-1",
        )

    assert store.load_acceptance("request-1") == canonical
    assert len(composer.calls) == 1


def test_committed_acceptance_replays_before_staleness_validation():
    service, composer, _, _ = registered_service()
    first = service.accept_idempotently(
        selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        acceptance_request_id="request-1",
    )
    service.clock = lambda: ACCEPTED_AT + timedelta(hours=3)

    replay = service.accept_idempotently(
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-retry",
        ),
        acceptance_request_id="request-1",
    )

    assert replay == first
    assert len(composer.calls) == 1


def test_stale_first_idempotent_acceptance_persists_nothing():
    stale = forecast_evidence(ACCEPTED_AT - timedelta(minutes=91))
    service, composer, store, _ = registered_service(evidence=stale)

    with pytest.raises(DecisionAcceptanceError, match="decision_context_stale"):
        service.accept_idempotently(
            selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
            acceptance_request_id="request-1",
        )

    assert store.load_acceptance("request-1") is None
    assert composer.calls == []


def test_idempotency_lookup_failure_uses_existing_persistence_error():
    service, composer, _, _ = registered_service()

    class FailingLookupStore:
        def load_acceptance(self, acceptance_request_id):
            raise OSError("read failed")

    service.context_store = FailingLookupStore()

    with pytest.raises(
        DecisionAcceptanceError,
        match="decision_lineage_persistence_error",
    ):
        service.accept_idempotently(
            selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
            acceptance_request_id="request-1",
        )

    assert composer.calls == []


def test_declined_idempotent_replay_preserves_selection_and_no_mission():
    service, composer, _, _ = registered_service()
    first = service.accept_idempotently(
        selection(UserSelectionSource.DECLINED, None),
        acceptance_request_id="request-declined",
    )
    replay = service.accept_idempotently(
        selection(
            UserSelectionSource.DECLINED,
            None,
            selection_id="selection-retry",
        ),
        acceptance_request_id="request-declined",
    )

    assert replay == first
    assert replay.selection.selection_id == "selection-1"
    assert replay.mission is None
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


@pytest.mark.parametrize(
    "retrieved_at",
    [
        ACCEPTED_AT - timedelta(minutes=90, microseconds=1),
        ACCEPTED_AT + timedelta(minutes=5, microseconds=1),
    ],
    ids=["too-old", "too-far-in-future"],
)
def test_stale_or_future_forecast_evidence_rejects_before_mission(retrieved_at):
    evidence = forecast_evidence(retrieved_at)
    service, composer, store, recommendation = registered_service(
        evidence=evidence
    )
    service.mission_id_factory = lambda: pytest.fail(
        "stale acceptance must stop before mission identity allocation"
    )
    before = store.load(decision_id="decision-1")

    with pytest.raises(DecisionAcceptanceError, match="decision_context_stale"):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))

    assert composer.calls == []
    assert store.load(decision_id="decision-1") == before
    assert recommendation.opportunity.candidate.catalog_key == "M31"
    assert evidence == forecast_evidence(retrieved_at)


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        DecisionForecastEvidence(()),
        forecast_evidence(
            ACCEPTED_AT - timedelta(minutes=20),
            ACCEPTED_AT - timedelta(minutes=10),
        ),
    ],
    ids=["missing", "empty", "inconsistent-retrieval-times"],
)
def test_unusable_forecast_evidence_fails_closed(evidence):
    service, composer, _, _ = registered_service(evidence=evidence)
    service.mission_id_factory = lambda: pytest.fail(
        "unusable evidence must stop before mission identity allocation"
    )

    with pytest.raises(DecisionAcceptanceError, match="decision_context_stale"):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))

    assert composer.calls == []


def test_expired_selected_window_rejects_before_mission():
    service, composer, _, _ = registered_service(
        window_end=ACCEPTED_AT - timedelta(microseconds=1)
    )
    service.mission_id_factory = lambda: pytest.fail(
        "expired window must stop before mission identity allocation"
    )

    with pytest.raises(DecisionAcceptanceError, match="decision_context_stale"):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))

    assert composer.calls == []


@pytest.mark.parametrize(
    "selected_at",
    [
        ACCEPTED_AT - timedelta(days=30),
        ACCEPTED_AT + timedelta(days=30),
    ],
    ids=["caller-past", "caller-future"],
)
def test_selected_at_cannot_override_authoritative_freshness_clock(selected_at):
    stale = forecast_evidence(ACCEPTED_AT - timedelta(minutes=91))
    service, composer, _, _ = registered_service(evidence=stale)
    service.mission_id_factory = lambda: pytest.fail(
        "caller time must not reach mission identity allocation"
    )

    with pytest.raises(DecisionAcceptanceError, match="decision_context_stale"):
        service.accept(selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selected_at=selected_at,
        ))

    assert composer.calls == []
