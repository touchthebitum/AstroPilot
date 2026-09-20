from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.night_mission import NightMission
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelectionStatus,
)
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
            imaging_field_id=selection.selected_imaging_field_id,
            acquisition_intent_id=selection.selected_acquisition_intent_id,
        )


def selection(
    source,
    target,
    *,
    selection_id="selection-1",
    decision_id="decision-1",
    selected_at=SELECTED_AT,
    selected_acquisition_intent_id=None,
):
    return UserSelection(
        selection_id=selection_id,
        decision_id=decision_id,
        selected_catalog_key=target,
        source=source,
        selected_at=selected_at,
        selected_acquisition_intent_id=selected_acquisition_intent_id,
    )


def registered_service(
    *,
    evidence=DEFAULT_EVIDENCE,
    accepted_at=ACCEPTED_AT,
    window_end=None,
    primary_imaging_field_id=None,
    alternative_imaging_field_id=None,
    primary_provenance=CandidateProvenance.PROJECT,
    profile_projects=None,
    primary_intent_provenance=(None, (), None),
    alternative_intent_provenance=(None, (), None),
    other_intent_provenance=None,
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
    def candidate(
        catalog_key,
        imaging_field_id=None,
        provenance=CandidateProvenance.PROJECT,
        intent_provenance=(None, (), None),
    ):
        selected_intent_id, viable_intent_ids, intent_status = intent_provenance
        return Candidate(
            name=catalog_key,
            catalog_key=catalog_key,
            priority=1.0,
            astro_score=80.0,
            final_score=80.0,
            decision_score=80.0,
            portfolio_score=80.0,
            global_score=80.0,
            setup_score=80.0,
            best_setup="setup",
            closure_bonus=0.0,
            provenance=provenance,
            imaging_field_id=imaging_field_id,
            selected_acquisition_intent_id=selected_intent_id,
            viable_acquisition_intent_ids=viable_intent_ids,
            acquisition_intent_selection_status=intent_status,
        )

    primary = candidate(
        "M31",
        primary_imaging_field_id,
        primary_provenance,
        primary_intent_provenance,
    )
    shortlist_entries = [
        primary,
        candidate(
            "M42",
            alternative_imaging_field_id,
            intent_provenance=alternative_intent_provenance,
        ),
    ]
    if other_intent_provenance is not None:
        shortlist_entries.append(
            candidate("M33", intent_provenance=other_intent_provenance)
        )
    recommendation = SimpleNamespace(
        opportunity=SimpleNamespace(
            candidate=primary,
            shortlist_entries=tuple(shortlist_entries),
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
        profile={
            "active_equipment": "setup",
            "projects": (
                {key: {} for key in ("M31", "M42", "M33")}
                if profile_projects is None
                else profile_projects
            ),
        },
        availability=None,
        primary_catalog_key="M31",
        exposed_alternative_catalog_keys=("M42",),
        explicitly_evaluated_catalog_keys=("M31", "M42", "M33"),
    )
    return service, composer, store, recommendation


def test_unique_candidate_intent_is_copied_when_request_omits_it():
    provenance = (
        "intent-A",
        ("intent-A",),
        AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
    )
    service, composer, store, recommendation = registered_service(
        primary_intent_provenance=provenance,
    )
    candidate = recommendation.opportunity.candidate
    scores_before = (candidate.final_score, candidate.decision_score, candidate.reasons)

    mission = service.accept(
        selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31")
    )

    stored = store.load_selection("selection-1")
    assert stored.selected_acquisition_intent_id == "intent-A"
    assert composer.calls[0]["selection"] is not candidate
    assert mission.selection_id == stored.selection_id == "selection-1"
    assert mission.acquisition_intent_id == "intent-A"
    assert (candidate.final_score, candidate.decision_score, candidate.reasons) == scores_before


def test_unique_candidate_intent_accepts_exact_same_request():
    provenance = (
        "intent-A",
        ("intent-A",),
        AcquisitionIntentSelectionStatus.PREFERRED,
    )
    service, _, store, _ = registered_service(
        primary_intent_provenance=provenance,
    )

    service.accept(selection(
        UserSelectionSource.PRIMARY_RECOMMENDATION,
        "M31",
        selected_acquisition_intent_id="intent-A",
    ))

    assert store.load_selection(
        "selection-1"
    ).selected_acquisition_intent_id == "intent-A"


def test_unique_candidate_intent_idempotent_replay_accepts_omission_or_same():
    service, composer, _, _ = registered_service(
        primary_intent_provenance=(
            "intent-A",
            ("intent-A",),
            AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
        ),
    )
    first = service.accept_idempotently(
        selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        acceptance_request_id="request-1",
    )
    omitted = service.accept_idempotently(
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-retry-1",
        ),
        acceptance_request_id="request-1",
    )
    same = service.accept_idempotently(
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-retry-2",
            selected_acquisition_intent_id="intent-A",
        ),
        acceptance_request_id="request-1",
    )

    assert omitted == same == first
    assert first.selection.selected_acquisition_intent_id == "intent-A"
    assert first.mission.acquisition_intent_id == "intent-A"
    assert len(composer.calls) == 1


def test_historical_none_intent_replay_keeps_canonical_lineage_unchanged():
    service, composer, store, _ = registered_service(
        primary_intent_provenance=(
            "intent-A",
            ("intent-A",),
            AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
        ),
    )
    historical_selection = selection(
        UserSelectionSource.PRIMARY_RECOMMENDATION,
        "M31",
    )
    historical_mission = composer.create(
        mission_id="mission-historical",
        selection=historical_selection,
    )
    store.commit_selection_and_mission(
        historical_selection,
        historical_mission,
        acceptance_request_id="request-historical",
    )
    composer.calls.clear()

    replay = service.accept_idempotently(
        selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selection_id="selection-retry",
        ),
        acceptance_request_id="request-historical",
    )

    assert replay.selection is not historical_selection
    assert replay.selection == historical_selection
    assert replay.selection.selected_acquisition_intent_id is None
    assert replay.mission == historical_mission
    assert composer.calls == []


def test_unique_candidate_intent_rejects_different_request_before_mission():
    service, composer, store, _ = registered_service(
        primary_intent_provenance=(
            "intent-A",
            ("intent-A",),
            AcquisitionIntentSelectionStatus.PREFERRED,
        ),
    )
    service.mission_id_factory = lambda: pytest.fail(
        "intent mismatch must stop before mission identity allocation"
    )

    with pytest.raises(
        DecisionAcceptanceError,
        match="selected_acquisition_intent_mismatch",
    ):
        service.accept(selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selected_acquisition_intent_id="intent-B",
        ))

    assert composer.calls == []
    with pytest.raises(DecisionAcceptanceError, match="selection_not_found"):
        store.load_selection("selection-1")


@pytest.mark.parametrize("intent_id", ["intent-A", "intent-B"])
def test_multiple_viable_intents_accept_exact_explicit_choice(intent_id):
    service, _, store, _ = registered_service(
        primary_intent_provenance=(
            None,
            ("intent-A", "intent-B"),
            AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE,
        ),
    )

    service.accept(selection(
        UserSelectionSource.PRIMARY_RECOMMENDATION,
        "M31",
        selected_acquisition_intent_id=intent_id,
    ))

    assert store.load_selection(
        "selection-1"
    ).selected_acquisition_intent_id == intent_id


@pytest.mark.parametrize(
    ("intent_id", "error"),
    [
        (None, "acquisition_intent_selection_required"),
        ("intent-C", "selected_acquisition_intent_not_viable"),
        (" intent-A ", "selected_acquisition_intent_not_viable"),
    ],
)
def test_multiple_viable_intents_never_fall_back_or_normalize(intent_id, error):
    service, composer, _, recommendation = registered_service(
        primary_intent_provenance=(
            None,
            ("intent-A", "intent-B"),
            AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE,
        ),
    )
    candidate = recommendation.opportunity.candidate
    identity_before = (
        candidate.selected_acquisition_intent_id,
        candidate.viable_acquisition_intent_ids,
        candidate.acquisition_intent_selection_status,
    )

    with pytest.raises(DecisionAcceptanceError, match=error):
        service.accept(selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selected_acquisition_intent_id=intent_id,
        ))

    assert composer.calls == []
    assert identity_before == (
        candidate.selected_acquisition_intent_id,
        candidate.viable_acquisition_intent_ids,
        candidate.acquisition_intent_selection_status,
    )


def test_no_viable_intent_rejects_mission_creation_and_provided_identity():
    provenance = (
        None,
        (),
        AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT,
    )
    blocked, composer, blocked_store, _ = registered_service(
        primary_imaging_field_id="sh2-129_ou4",
        profile_projects={"M31": {"imaging_field_id": "sh2-129_ou4"}},
        primary_intent_provenance=provenance,
    )
    with pytest.raises(
        DecisionAcceptanceError,
        match="acquisition_intent_required_for_mission",
    ):
        blocked.accept(
            selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31")
        )
    assert composer.calls == []
    with pytest.raises(DecisionAcceptanceError, match="selection_not_found"):
        blocked_store.load_selection("selection-1")

    rejected, composer, _, _ = registered_service(
        primary_intent_provenance=provenance,
    )
    with pytest.raises(
        DecisionAcceptanceError,
        match="selected_acquisition_intent_not_available",
    ):
        rejected.accept(selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selected_acquisition_intent_id="intent-A",
        ))
    assert composer.calls == []


def test_incoherent_single_viable_without_selected_intent_fails_closed():
    service, composer, store, _ = registered_service()
    candidate = store._contexts[
        "decision-1"
    ].recommendation.opportunity.candidate
    candidate.acquisition_intent_selection_status = (
        AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE
    )
    candidate.viable_acquisition_intent_ids = ("intent-A",)

    with pytest.raises(
        DecisionAcceptanceError,
        match="invalid_acquisition_intent_selection_provenance",
    ):
        service.accept(selection(
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            selected_acquisition_intent_id="intent-A",
        ))

    assert composer.calls == []


def test_legacy_candidate_and_other_evaluated_target_keep_none_intent():
    service, _, store, _ = registered_service()

    mission = service.accept(
        selection(UserSelectionSource.OTHER_EVALUATED_TARGET, "M33")
    )

    assert store.load_selection(
        "selection-1"
    ).selected_acquisition_intent_id is None
    assert mission.acquisition_intent_id is None


def test_modern_other_target_without_resolved_intent_rejects_before_allocation():
    service, composer, store, _ = registered_service(
        profile_projects={"M33": {"imaging_field_id": "sh2-129_ou4"}},
        other_intent_provenance=(
            None,
            (),
            AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT,
        ),
    )
    service.mission_id_factory = lambda: pytest.fail(
        "missing modern intent must stop before mission identity allocation"
    )

    with pytest.raises(
        DecisionAcceptanceError,
        match="acquisition_intent_required_for_mission",
    ):
        service.accept(
            selection(UserSelectionSource.OTHER_EVALUATED_TARGET, "M33")
        )

    assert composer.calls == []
    with pytest.raises(DecisionAcceptanceError, match="selection_not_found"):
        store.load_selection("selection-1")


def test_modern_other_target_propagates_resolved_intent_to_mission():
    service, composer, store, _ = registered_service(
        profile_projects={"M33": {"imaging_field_id": "sh2-129_ou4"}},
        other_intent_provenance=(
            "intent-A",
            ("intent-A",),
            AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
        ),
    )

    mission = service.accept(
        selection(UserSelectionSource.OTHER_EVALUATED_TARGET, "M33")
    )

    stored = store.load_selection("selection-1")
    assert stored.selected_acquisition_intent_id == "intent-A"
    assert composer.calls[0]["selection"] == stored
    assert mission.acquisition_intent_id == "intent-A"


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


@pytest.mark.parametrize(
    ("source", "target", "service_kwargs"),
    [
        (
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            {
                "primary_imaging_field_id": "sh2-129_ou4",
                "profile_projects": {
                    "M31": {"imaging_field_id": "sh2-129_ou4"}
                },
            },
        ),
        (
            UserSelectionSource.ALTERNATIVE,
            "M42",
            {
                "alternative_imaging_field_id": "sh2-129_ou4",
                "profile_projects": {
                    "M42": {"imaging_field_id": "sh2-129_ou4"}
                },
            },
        ),
        (
            UserSelectionSource.OTHER_EVALUATED_TARGET,
            "M33",
            {
                "profile_projects": {
                    "M33": {"imaging_field_id": "sh2-129_ou4"}
                },
            },
        ),
    ],
)
def test_acceptance_persists_canonical_selected_imaging_field(
    source,
    target,
    service_kwargs,
):
    service, composer, store, _ = registered_service(**service_kwargs)

    service.accept(selection(source, target))
    stored = store.load_selection("selection-1")

    assert stored.selected_imaging_field_id == "sh2-129_ou4"
    assert store.load_mission("mission-1").imaging_field_id == "sh2-129_ou4"
    assert composer.calls[0]["selection"] == stored


@pytest.mark.parametrize(
    ("source", "target", "service_kwargs"),
    [
        (
            UserSelectionSource.PRIMARY_RECOMMENDATION,
            "M31",
            {"primary_provenance": CandidateProvenance.DISCOVERY},
        ),
        (UserSelectionSource.OTHER_EVALUATED_TARGET, "M33", {}),
        (UserSelectionSource.DECLINED, None, {}),
    ],
)
def test_discovery_legacy_and_declined_persist_no_imaging_field(
    source,
    target,
    service_kwargs,
):
    service, _, store, _ = registered_service(**service_kwargs)

    service.accept(selection(source, target))

    assert store.load_selection("selection-1").selected_imaging_field_id is None
    if source is not UserSelectionSource.DECLINED:
        assert store.load_mission("mission-1").imaging_field_id is None


def test_mission_imaging_field_mismatch_fails_before_commit():
    service, composer, store, _ = registered_service(
        primary_imaging_field_id="sh2-129_ou4",
        profile_projects={"M31": {"imaging_field_id": "sh2-129_ou4"}},
    )
    original_create = composer.create

    def create_mismatched(**kwargs):
        return replace(
            original_create(**kwargs),
            imaging_field_id="different-field",
        )

    composer.create = create_mismatched

    with pytest.raises(
        DecisionAcceptanceError,
        match="mission_imaging_field_mismatch",
    ):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))

    with pytest.raises(DecisionAcceptanceError, match="selection_not_found"):
        store.load_selection("selection-1")


def test_mission_acquisition_intent_mismatch_fails_before_commit():
    service, composer, store, _ = registered_service(
        primary_intent_provenance=(
            "intent-A",
            ("intent-A",),
            AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
        ),
    )
    original_create = composer.create

    def create_mismatched(**kwargs):
        return replace(
            original_create(**kwargs),
            acquisition_intent_id="intent-B",
        )

    composer.create = create_mismatched

    with pytest.raises(
        DecisionAcceptanceError,
        match="mission_acquisition_intent_mismatch",
    ):
        service.accept(
            selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31")
        )

    with pytest.raises(DecisionAcceptanceError, match="selection_not_found"):
        store.load_selection("selection-1")


def test_candidate_profile_mismatch_fails_before_allocation_or_commit():
    service, composer, store, _ = registered_service(
        primary_imaging_field_id="sh2-129_ou4",
    )
    service.mission_id_factory = lambda: pytest.fail(
        "mismatch must stop before mission identity allocation"
    )
    before = store.load(decision_id="decision-1")

    with pytest.raises(
        DecisionAcceptanceError,
        match="selected_imaging_field_mismatch",
    ):
        service.accept(selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"))

    assert composer.calls == []
    assert store.load(decision_id="decision-1") == before


def test_invalid_project_imaging_field_fails_closed_before_commit():
    service, composer, store, _ = registered_service(
        profile_projects={"M33": {"imaging_field_id": "unknown"}},
    )
    service.mission_id_factory = lambda: pytest.fail(
        "invalid reference must stop before mission identity allocation"
    )

    with pytest.raises(
        DecisionAcceptanceError,
        match="invalid_selected_imaging_field_reference",
    ):
        service.accept(
            selection(UserSelectionSource.OTHER_EVALUATED_TARGET, "M33")
        )

    assert composer.calls == []
    with pytest.raises(DecisionAcceptanceError, match="selection_not_found"):
        store.load_selection("selection-1")


def test_first_idempotent_acceptance_and_replay_return_canonical_lineage():
    service, composer, store, recommendation = registered_service(
        primary_imaging_field_id="sh2-129_ou4",
        profile_projects={"M31": {"imaging_field_id": "sh2-129_ou4"}},
    )

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
    assert replay.mission.imaging_field_id == replay.selection.selected_imaging_field_id
    assert replay.mission.imaging_field_id == "sh2-129_ou4"
    assert (
        replay.mission.acquisition_intent_id
        == replay.selection.selected_acquisition_intent_id
    )
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
