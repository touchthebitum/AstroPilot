import json
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone
from inspect import getsource
from uuid import UUID

import pytest

import astropilot.user_profile as user_profile
from astropilot.decision_forecast_evidence_store import (
    FileDecisionForecastEvidenceStore,
)
from astropilot.decision_acceptance_lineage_store import (
    FileDecisionAcceptanceLineageStore,
)
from astropilot.execution_lineage_store import FileExecutionLineageStore
from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
)
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.models.portfolio_credit import PortfolioCredit
from decision.models.portfolio_credit_application import (
    PortfolioCreditApplication,
    PortfolioCreditApplicationOutcome,
    PortfolioCreditDestinationKind,
)
import decision.services.durable_tonight_application_service as durable_module
from decision.services.durable_tonight_application_service import (
    DurableTonightApplicationService,
    generate_decision_id,
)
from decision.services.execution_outcome_application import (
    ExecutionOutcomeApplicationError,
    ExecutionOutcomeApplicationService,
)
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceContext,
)
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
)
from decision.services.tonight_application_service import (
    TonightResult,
    TonightStatus,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


FORECAST_AT = datetime(2026, 8, 31, 21, tzinfo=timezone.utc)
SITE = WeatherLocation(46.75, 6.55, altitude_m=1_245.0)
EVIDENCE = DecisionForecastEvidence(
    (
        WeatherForecastPoint(
            provider_id="open_meteo",
            model_id="best_match",
            retrieved_at_utc=FORECAST_AT.replace(hour=18),
            forecast_for_utc=FORECAST_AT,
            requested_location=SITE,
            grid_location=SITE,
            values=(
                WeatherValue(
                    WeatherVariable.TEMPERATURE_C,
                    8.25,
                    "°C",
                ),
            ),
        ),
    )
)


class FakeApplicationService:
    tonight_mission_service = object()

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def evaluate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result

    @staticmethod
    def build_mission_input(*args, **kwargs):
        raise AssertionError("acceptance mission creation is not used here")


class FakeStore:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def save(self, *, decision_id, evidence):
        self.calls.append((decision_id, evidence))
        if self.error is not None:
            raise self.error


class IdFactory:
    def __init__(self, *identities, error=None):
        self.identities = iter(identities)
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return next(self.identities)


def result(*, status=TonightStatus.AVAILABLE, evidence=EVIDENCE):
    return TonightResult(
        night={"date": "2026-08-31"},
        recommendation=object(),
        mission=object(),
        status=status,
        forecast_evidence=evidence,
    )


def wrapper(source_result, *, store=None, factory=None):
    application_service = FakeApplicationService(source_result)
    evidence_store = store or FakeStore()
    decision_id_factory = factory or IdFactory("decision-123")
    service = DurableTonightApplicationService(
        application_service=application_service,
        evidence_store=evidence_store,
        decision_id_factory=decision_id_factory,
    )
    return service, application_service, evidence_store, decision_id_factory


def test_available_result_is_persisted_once_and_structurally_enriched():
    original = result()
    service, application, store, factory = wrapper(original)
    arguments = {
        "profile": {"location": {"name": "Buttes"}},
        "weather": object(),
        "reference_time_utc": FORECAST_AT,
        "goal": "balanced",
    }

    durable = service.evaluate(**arguments)

    assert application.calls == [arguments]
    assert factory.calls == 1
    assert store.calls == [("decision-123", original.forecast_evidence)]
    assert store.calls[0][1] is original.forecast_evidence
    assert durable is not original
    assert durable.decision_id == "decision-123"
    assert durable.night is original.night
    assert durable.recommendation is original.recommendation
    assert durable.mission is original.mission
    assert durable.status is original.status
    assert durable.forecast_evidence is original.forecast_evidence
    assert original.decision_id is None


def test_result_without_evidence_returns_unchanged_without_id_or_save():
    original = result(
        status=TonightStatus.FORECAST_UNAVAILABLE,
        evidence=None,
    )
    service, application, store, factory = wrapper(original)

    returned = service.evaluate(profile={}, weather=None)

    assert returned is original
    assert returned.decision_id is None
    assert len(application.calls) == 1
    assert factory.calls == 0
    assert store.calls == []


@pytest.mark.parametrize(
    "status",
    [
        TonightStatus.NO_NIGHT,
        TonightStatus.NO_MISSION,
        TonightStatus.NO_PRODUCTIVE_WINDOW,
    ],
)
def test_partial_or_negative_result_with_evidence_is_persisted(status):
    original = result(status=status)
    service, _, store, factory = wrapper(original)

    durable = service.evaluate(profile={})

    assert durable.status is status
    assert durable.decision_id == "decision-123"
    assert factory.calls == 1
    assert store.calls == [("decision-123", EVIDENCE)]


def test_application_service_failure_prevents_id_and_save():
    application_error = RuntimeError("evaluation_failed")
    application = FakeApplicationService(error=application_error)
    store = FakeStore()
    factory = IdFactory("decision-123")
    service = DurableTonightApplicationService(
        application_service=application,
        evidence_store=store,
        decision_id_factory=factory,
    )

    with pytest.raises(RuntimeError, match="evaluation_failed"):
        service.evaluate(profile={})

    assert len(application.calls) == 1
    assert factory.calls == 0
    assert store.calls == []


def test_id_factory_failure_prevents_save():
    factory = IdFactory(error=RuntimeError("identity_failed"))
    service, _, store, _ = wrapper(result(), factory=factory)

    with pytest.raises(RuntimeError, match="identity_failed"):
        service.evaluate(profile={})

    assert factory.calls == 1
    assert store.calls == []


def test_store_failure_is_propagated_without_retry_or_durable_result():
    store = FakeStore(error=RuntimeError("save_failed"))
    service, application, _, factory = wrapper(result(), store=store)

    with pytest.raises(RuntimeError, match="save_failed"):
        service.evaluate(profile={})

    assert len(application.calls) == 1
    assert factory.calls == 1
    assert store.calls == [("decision-123", EVIDENCE)]


def test_same_evidence_in_two_evaluations_creates_two_events():
    original = result()
    store = FakeStore()
    factory = IdFactory("decision-1", "decision-2")
    service, application, _, _ = wrapper(
        original,
        store=store,
        factory=factory,
    )

    first = service.evaluate(profile={})
    second = service.evaluate(profile={})

    assert first.decision_id == "decision-1"
    assert second.decision_id == "decision-2"
    assert len(application.calls) == 2
    assert factory.calls == 2
    assert store.calls == [
        ("decision-1", EVIDENCE),
        ("decision-2", EVIDENCE),
    ]


def test_tonight_result_remains_immutable():
    original = result()

    with pytest.raises(FrozenInstanceError):
        original.decision_id = "changed"


def test_invalid_id_validation_is_delegated_to_store(tmp_path):
    real_store = FileDecisionForecastEvidenceStore(tmp_path)
    service, _, _, factory = wrapper(
        result(),
        store=real_store,
        factory=IdFactory("../invalid"),
    )

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_decision_id",
    ):
        service.evaluate(profile={})

    assert factory.calls == 1
    assert list(tmp_path.iterdir()) == []


def test_production_id_factory_returns_distinct_canonical_uuid4_strings():
    first = generate_decision_id()
    second = generate_decision_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    assert first != second
    assert UUID(first).version == 4
    assert UUID(second).version == 4
    assert str(UUID(first)) == first
    assert str(UUID(second)) == second


def test_wrapper_has_no_clock_network_or_domain_specific_dependency():
    source = getsource(durable_module)

    assert "datetime" not in source
    assert "requests" not in source
    assert "meteoswiss" not in source.lower()
    assert "field_validation" not in source
    assert "provider_reliability" not in source


CREDIT_START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
CREDIT_END = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)
CREDIT_DURATION = timedelta(hours=3)
USABLE_DURATION = timedelta(hours=1, minutes=15)


def credit_mission():
    return NightMission(
        target="M31",
        confidence="HIGH",
        equipment=["setup"],
        site_name="Mont Sujet",
        mission_id="mission-credit",
        decision_id="decision-credit",
        selection_id="selection-credit",
    )


def terminal_execution(status, execution_id="execution-credit"):
    return Execution(
        execution_id=execution_id,
        mission_id="mission-credit",
        status=status,
        actual_start=CREDIT_START,
        actual_end=CREDIT_END,
        actual_duration=CREDIT_DURATION,
    )


def acquisition_evidence(
    evidence_id="evidence-credit",
    execution_id="execution-credit",
):
    return AcquisitionOutcomeEvidence(
        evidence_id=evidence_id,
        execution_id=execution_id,
        category=OutcomeEvidenceCategory.ACQUISITION,
        observed_at=CREDIT_END,
        source=OutcomeEvidenceSource.USER,
        actual_capture_duration=timedelta(hours=2, minutes=45),
        usable_integration_duration=USABLE_DURATION,
    )


def portfolio_credit(
    credit_id="credit-1",
    evidence_id="evidence-credit",
    execution_id="execution-credit",
):
    return PortfolioCredit(
        credit_id=credit_id,
        execution_id=execution_id,
        evidence_ids=(evidence_id,),
        usable_integration_duration=USABLE_DURATION,
        credited_at=CREDIT_END,
    )


def credit_application(credit_id="credit-1", object_name="M31"):
    return PortfolioCreditApplication(
        application_id=f"application-{credit_id}",
        credit_id=credit_id,
        object_name=object_name,
        destination_kind=PortfolioCreditDestinationKind.PROJECT,
        applied_duration=USABLE_DURATION,
        applied_at=CREDIT_END,
    )


def profile_callbacks(profile_path):
    def load_profile():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile.setdefault("profile_revision", 0)
        return profile

    def save_profile(profile, *, expected_revision):
        current = json.loads(profile_path.read_text(encoding="utf-8"))
        current_revision = current.get("profile_revision", 0)
        if expected_revision != current_revision:
            raise user_profile.ProfileRevisionConflictError(
                "profile_revision_conflict"
            )
        candidate = json.loads(json.dumps(profile))
        if candidate.get("profile_revision", 0) != expected_revision:
            raise user_profile.ProfileRevisionConflictError(
                "profile_revision_conflict"
            )
        candidate["profile_revision"] = expected_revision + 1
        profile_path.write_text(json.dumps(candidate), encoding="utf-8")

    return load_profile, save_profile


def composed_credit_service(tmp_path, status=ExecutionStatus.COMPLETED):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "projects": {
                    "M31": {
                        "hours": 2.0,
                        "target_hours": 20.0,
                        "importance": 8,
                    }
                },
                "sessions": [],
            }
        ),
        encoding="utf-8",
    )
    load_profile, save_profile = profile_callbacks(profile_path)
    outer = DurableTonightApplicationService(
        application_service=FakeApplicationService(),
        evidence_store=FakeStore(),
        decision_id_factory=IdFactory("unused"),
        profile_loader=load_profile,
        profile_saver=save_profile,
    )
    mission = credit_mission()
    execution_service = ExecutionOutcomeApplicationService(
        mission_loader=lambda mission_id: (
            mission if mission_id == mission.mission_id else None
        )
    )
    execution_service.create_execution(
        execution_id="execution-credit",
        mission_id="mission-credit",
    )
    execution_service.transition_execution(
        Execution(
            execution_id="execution-credit",
            mission_id="mission-credit",
            status=ExecutionStatus.IN_PROGRESS,
            actual_start=CREDIT_START,
            actual_end=None,
            actual_duration=None,
        )
    )
    source_execution = terminal_execution(status)
    execution_service.transition_execution(source_execution)
    source_evidence = acquisition_evidence()
    execution_service.record_outcome_evidence(
        execution_id="execution-credit",
        evidence=source_evidence,
    )
    outer._execution_outcome_service = execution_service
    return (
        outer,
        execution_service,
        profile_path,
        source_execution,
        source_evidence,
    )


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED],
)
def test_composed_credit_uses_exact_v1_execution_and_evidence(tmp_path, status):
    outer, execution_service, profile_path, source_execution, source_evidence = (
        composed_credit_service(tmp_path, status)
    )
    execution_calls = []
    evidence_calls = []
    load_execution = execution_service.load_execution
    load_evidence = execution_service.load_outcome_evidence

    def observed_execution_loader(execution_id):
        loaded = load_execution(execution_id)
        execution_calls.append((execution_id, loaded))
        return loaded

    def observed_evidence_loader(evidence_id):
        loaded = load_evidence(evidence_id)
        evidence_calls.append((evidence_id, loaded))
        return loaded

    execution_service.load_execution = observed_execution_loader
    execution_service.load_outcome_evidence = observed_evidence_loader
    execution_before = asdict(source_execution)
    evidence_before = asdict(source_evidence)
    credit = portfolio_credit()
    credit_before = asdict(credit)

    applied = outer.apply_portfolio_credit(credit_application(), credit)
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert applied.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert execution_calls == [("execution-credit", source_execution)]
    assert execution_calls[0][1] is source_execution
    assert evidence_calls == [("evidence-credit", source_evidence)]
    assert evidence_calls[0][1] is source_evidence
    assert persisted["projects"]["M31"]["hours"] == 3.25
    assert persisted["projects"]["M31"]["hours"] != 5.0
    assert persisted["projects"]["M31"]["hours"] != 4.75
    assert persisted["sessions"] == []
    assert set(persisted["projects"]) == {"M31"}
    assert not any(
        key in persisted
        for key in (
            "outcome_assessments",
            "learning_eligibility",
            "learning_signals",
            "learning_applications",
        )
    )
    assert asdict(source_execution) == execution_before
    assert asdict(source_evidence) == evidence_before
    assert asdict(credit) == credit_before
    assert not hasattr(outer, "outcome_assessment")
    assert not hasattr(outer, "learning")


def test_composed_credit_missing_execution_and_evidence_fail_closed(tmp_path):
    outer, execution_service, profile_path, _, _ = composed_credit_service(tmp_path)
    before = profile_path.read_bytes()

    execution_service._executions.clear()
    with pytest.raises(ValueError, match="execution_not_found"):
        outer.apply_portfolio_credit(credit_application(), portfolio_credit())
    assert profile_path.read_bytes() == before

    outer._portfolio_credit_service = None
    execution_service._executions["execution-credit"] = terminal_execution(
        ExecutionStatus.COMPLETED
    )
    execution_service._evidence.clear()
    with pytest.raises(ValueError, match="evidence_not_found"):
        outer.apply_portfolio_credit(credit_application(), portfolio_credit())
    assert profile_path.read_bytes() == before


def test_composed_credit_rejects_cross_execution_evidence(tmp_path):
    outer, execution_service, profile_path, _, _ = composed_credit_service(tmp_path)
    cross_evidence = acquisition_evidence(
        evidence_id="evidence-cross",
        execution_id="execution-other",
    )
    execution_service.create_execution(
        execution_id="execution-other",
        mission_id="mission-credit",
    )
    execution_service.record_outcome_evidence(
        execution_id="execution-other",
        evidence=cross_evidence,
    )
    before = profile_path.read_bytes()

    with pytest.raises(ValueError, match="evidence_execution_mismatch"):
        outer.apply_portfolio_credit(
            credit_application(),
            portfolio_credit(evidence_id="evidence-cross"),
        )

    assert profile_path.read_bytes() == before


def test_composed_credit_does_not_fabricate_an_unknown_project(tmp_path):
    outer, _, profile_path, _, _ = composed_credit_service(tmp_path)
    before = profile_path.read_bytes()

    with pytest.raises(ValueError, match="project_destination_unresolved"):
        outer.apply_portfolio_credit(
            credit_application(object_name="NGC7000"),
            portfolio_credit(),
        )

    assert profile_path.read_bytes() == before


def test_composed_replay_survives_service_reconstruction(tmp_path):
    outer, _, profile_path, _, _ = composed_credit_service(tmp_path)
    first = outer.apply_portfolio_credit(credit_application(), portfolio_credit())
    same_service_replay = outer.apply_portfolio_credit(
        credit_application(),
        portfolio_credit(),
    )
    load_profile, save_profile = profile_callbacks(profile_path)
    reconstructed = DurableTonightApplicationService(
        application_service=FakeApplicationService(),
        evidence_store=FakeStore(),
        decision_id_factory=IdFactory("unused"),
        profile_loader=load_profile,
        profile_saver=save_profile,
    )
    reconstructed._execution_outcome_service = ExecutionOutcomeApplicationService(
        mission_loader=lambda _: None
    )

    reconstructed_replay = reconstructed.apply_portfolio_credit(
        credit_application(),
        portfolio_credit(),
    )
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert first.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert same_service_replay.outcome is PortfolioCreditApplicationOutcome.ALREADY_APPLIED
    assert reconstructed_replay.outcome is PortfolioCreditApplicationOutcome.ALREADY_APPLIED
    assert persisted["projects"]["M31"]["hours"] == 3.25


def test_composed_distinct_credits_apply_independently(tmp_path):
    outer, execution_service, profile_path, _, _ = composed_credit_service(tmp_path)
    second_evidence = acquisition_evidence(evidence_id="evidence-credit-2")
    execution_service.record_outcome_evidence(
        execution_id="execution-credit",
        evidence=second_evidence,
    )

    outer.apply_portfolio_credit(credit_application(), portfolio_credit())
    outer.apply_portfolio_credit(
        credit_application("credit-2"),
        portfolio_credit("credit-2", evidence_id="evidence-credit-2"),
    )
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert persisted["projects"]["M31"]["hours"] == 4.5
    assert set(persisted["portfolio_credit_applications"]) == {
        "credit-1",
        "credit-2",
    }


def test_composed_credit_never_calls_legacy_record_session(
    tmp_path,
    monkeypatch,
):
    outer, _, profile_path, _, _ = composed_credit_service(tmp_path)

    def forbidden_record_session(*args, **kwargs):
        pytest.fail("V1 credit composition must not call record_session")

    monkeypatch.setattr(user_profile, "record_session", forbidden_record_session)

    outer.apply_portfolio_credit(credit_application(), portfolio_credit())
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert persisted["sessions"] == []
    assert persisted["projects"]["M31"]["hours"] == 3.25


def test_production_factory_supplies_canonical_profile_callbacks():
    import astro_score

    service = astro_score.build_durable_tonight_application_service()

    assert service.profile_loader is astro_score.load_user_profile
    assert service.profile_saver is astro_score.save_user_profile


def durable_acceptance_lineage(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path / "decision_lineage")
    context = DecisionAcceptanceContext(
        decision_context=UserSelectionDecisionContext(
            decision_id="decision-credit",
            primary_catalog_key="M31",
            exposed_alternative_catalog_keys=(),
            explicitly_evaluated_catalog_keys=("M31",),
        ),
        recommendation={"catalog_key": "M31"},
        night={},
        profile={},
        availability=None,
    )
    selection = UserSelection(
        selection_id="selection-credit",
        decision_id="decision-credit",
        selected_catalog_key="M31",
        source=UserSelectionSource.PRIMARY_RECOMMENDATION,
        selected_at=CREDIT_START,
    )
    mission = NightMission(
        target="M31",
        confidence="HIGH",
        equipment=["setup"],
        recommended_hours=3.0,
        site_name="Mont Sujet",
        mission_id="mission-credit",
        decision_id="decision-credit",
        selection_id="selection-credit",
    )
    store.create_context(context)
    store.commit_selection_and_mission(selection, mission)
    return store, mission


def reconstructed_lineage_service(tmp_path, profile_path):
    load_profile, save_profile = profile_callbacks(profile_path)
    return DurableTonightApplicationService(
        application_service=FakeApplicationService(),
        evidence_store=FileDecisionForecastEvidenceStore(
            tmp_path / "decision_forecast_evidence"
        ),
        decision_id_factory=IdFactory("unused"),
        acceptance_lineage_store=FileDecisionAcceptanceLineageStore(
            tmp_path / "decision_lineage"
        ),
        execution_lineage_store=FileExecutionLineageStore(
            tmp_path / "execution_lineage"
        ),
        profile_loader=load_profile,
        profile_saver=save_profile,
    )


def test_gp08_new_credit_uses_durable_execution_and_evidence_after_reconstruction(
    tmp_path,
    monkeypatch,
):
    _, mission = durable_acceptance_lineage(tmp_path)
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps({
            "projects": {
                "M31": {"hours": 2.0, "target_hours": 20.0, "importance": 8}
            },
            "sessions": [],
        }),
        encoding="utf-8",
    )
    execution_start = CREDIT_START
    execution_end = execution_start + timedelta(hours=1, minutes=12)
    usable_duration = timedelta(hours=1, minutes=12)
    capture_duration = timedelta(hours=2, minutes=45)
    first = reconstructed_lineage_service(tmp_path, profile_path)
    first.create_execution(
        execution_id="execution-credit",
        mission_id=mission.mission_id,
    )
    first.transition_execution(Execution(
        execution_id="execution-credit",
        mission_id=mission.mission_id,
        status=ExecutionStatus.IN_PROGRESS,
        actual_start=execution_start,
        actual_end=None,
        actual_duration=None,
    ))
    interrupted = Execution(
        execution_id="execution-credit",
        mission_id=mission.mission_id,
        status=ExecutionStatus.INTERRUPTED,
        actual_start=execution_start,
        actual_end=execution_end,
        actual_duration=usable_duration,
    )
    first.transition_execution(interrupted)
    source_evidence = AcquisitionOutcomeEvidence(
        evidence_id="evidence-credit",
        execution_id="execution-credit",
        category=OutcomeEvidenceCategory.ACQUISITION,
        observed_at=execution_end,
        source=OutcomeEvidenceSource.USER,
        actual_capture_duration=capture_duration,
        usable_integration_duration=usable_duration,
    )
    first.record_outcome_evidence(
        execution_id="execution-credit",
        evidence=source_evidence,
    )

    def forbidden_record_session(*args, **kwargs):
        pytest.fail("durable V1 credit must not call record_session")

    monkeypatch.setattr(user_profile, "record_session", forbidden_record_session)
    reconstructed = reconstructed_lineage_service(tmp_path, profile_path)
    credit = PortfolioCredit(
        credit_id="credit-reconstructed",
        execution_id="execution-credit",
        evidence_ids=("evidence-credit",),
        usable_integration_duration=usable_duration,
        credited_at=execution_end,
    )
    application = PortfolioCreditApplication(
        application_id="application-reconstructed",
        credit_id=credit.credit_id,
        object_name="M31",
        destination_kind=PortfolioCreditDestinationKind.PROJECT,
        applied_duration=usable_duration,
        applied_at=execution_end,
    )

    assert reconstructed.load_execution("execution-credit") == interrupted
    assert type(reconstructed.load_outcome_evidence("evidence-credit")) is (
        AcquisitionOutcomeEvidence
    )
    applied = reconstructed.apply_portfolio_credit(application, credit)
    persisted_after_apply = json.loads(profile_path.read_text(encoding="utf-8"))

    replayed = reconstructed_lineage_service(
        tmp_path,
        profile_path,
    ).apply_portfolio_credit(application, credit)
    persisted_after_replay = json.loads(profile_path.read_text(encoding="utf-8"))

    assert mission.recommended_hours == 3.0
    assert interrupted.actual_duration == timedelta(hours=1, minutes=12)
    assert source_evidence.actual_capture_duration == capture_duration
    assert source_evidence.usable_integration_duration == usable_duration
    assert applied.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert persisted_after_apply["projects"]["M31"]["hours"] == 3.2
    assert persisted_after_apply["projects"]["M31"]["hours"] != 5.0
    assert persisted_after_apply["projects"]["M31"]["hours"] != 4.75
    assert replayed.outcome is PortfolioCreditApplicationOutcome.ALREADY_APPLIED
    assert persisted_after_replay["projects"]["M31"]["hours"] == 3.2
    assert persisted_after_replay["sessions"] == []


def test_reconstructed_execution_commands_fail_closed(tmp_path):
    _, mission = durable_acceptance_lineage(tmp_path)
    store = FileExecutionLineageStore(tmp_path / "execution_lineage")
    application = ExecutionOutcomeApplicationService(
        mission_loader=lambda mission_id: mission if mission_id == mission.mission_id else None,
        lineage_store=store,
    )

    with pytest.raises(ExecutionOutcomeApplicationError, match="execution_not_found"):
        application.transition_execution(terminal_execution(ExecutionStatus.COMPLETED))
    assert application.load_execution("missing") is None
    assert application.load_outcome_evidence("missing") is None

    application.create_execution(
        execution_id="execution-credit",
        mission_id="mission-credit",
    )
    with pytest.raises(
        ExecutionOutcomeApplicationError,
        match="evidence_execution_mismatch",
    ):
        application.record_outcome_evidence(
            execution_id="execution-credit",
            evidence=acquisition_evidence(execution_id="execution-other"),
        )


def test_stale_transition_and_persistence_failure_do_not_report_success(tmp_path):
    _, mission = durable_acceptance_lineage(tmp_path)
    backing = FileExecutionLineageStore(tmp_path / "execution_lineage")

    class InterferingStore:
        def create_execution(self, source):
            return backing.create_execution(source)

        def load_execution(self, execution_id):
            return backing.load_execution(execution_id)

        def replace_execution(self, destination, *, expected_execution):
            backing.replace_execution(
                Execution(
                    execution_id="execution-credit",
                    mission_id="mission-credit",
                    status=ExecutionStatus.UNCONFIRMED,
                    actual_start=None,
                    actual_end=None,
                    actual_duration=None,
                ),
                expected_execution=expected_execution,
            )
            return backing.replace_execution(
                destination,
                expected_execution=expected_execution,
            )

        def append_evidence(self, source):
            return backing.append_evidence(source)

        def load_evidence(self, evidence_id):
            return backing.load_evidence(evidence_id)

    application = ExecutionOutcomeApplicationService(
        mission_loader=lambda _: mission,
        lineage_store=InterferingStore(),
    )
    application.create_execution(
        execution_id="execution-credit",
        mission_id="mission-credit",
    )

    with pytest.raises(ExecutionOutcomeApplicationError, match="execution_stale_state"):
        application.transition_execution(Execution(
            execution_id="execution-credit",
            mission_id="mission-credit",
            status=ExecutionStatus.IN_PROGRESS,
            actual_start=CREDIT_START,
            actual_end=None,
            actual_duration=None,
        ))
    assert backing.load_execution("execution-credit").status is (
        ExecutionStatus.UNCONFIRMED
    )

    class FailingStore(InterferingStore):
        def create_execution(self, source):
            raise OSError("write failed")

    failing = ExecutionOutcomeApplicationService(
        mission_loader=lambda _: mission,
        lineage_store=FailingStore(),
    )
    with pytest.raises(OSError, match="write failed"):
        failing.create_execution(
            execution_id="execution-failing",
            mission_id="mission-credit",
        )
