import ast
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import decision.services.outcome_evaluation_orchestration as orchestration_module
from astropilot.field_observation_store import FileFieldObservationStore
from astropilot.decision_forecast_evidence_store import (
    FileDecisionForecastEvidenceStore,
)
from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
from decision.field_observation import (
    CaptureMethod,
    Confidence,
    FieldObservation,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
)
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
    serialize_field_observation,
)
from decision.models.forecast_observation_comparison import (
    ForecastObservationComparisonStatus,
)
from decision.models.outcome_assessment import OutcomeAssessmentStatus
from decision.models.outcome_evaluation import (
    ForecastComparisonOutcomeEvidenceSourceType,
)
from decision.services.outcome_evaluation_orchestration import (
    OutcomeEvaluationOrchestrationError,
    OutcomeEvaluationOrchestrationService,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)
FIRST_COMPUTED_AT = datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
SECOND_COMPUTED_AT = FIRST_COMPUTED_AT + timedelta(hours=1)
LOCATION = WeatherLocation(46.75, 6.55, altitude_m=1245.0)


def observation(**overrides):
    values = {
        "observation_id": "observation-1",
        "decision_id": "decision-1",
        "execution_id": "execution-1",
        "observed_at_utc": OBSERVED_AT,
        "recorded_at_utc": OBSERVED_AT + timedelta(minutes=1),
        "supersedes_observation_id": None,
        "conditions": ObservedConditions(temperature_c=7.0),
        "acquisition": ObservedAcquisition(),
        "technical": ObservedTechnical(),
        "provenance": ObservationProvenance(
            source_type=ObservationSourceType.WEATHER_STATION,
            capture_method=CaptureMethod.AUTOMATIC,
            source_id="station-1",
        ),
        "quality": ObservationQuality(confidence=Confidence.HIGH),
    }
    values.update(overrides)
    return FieldObservation(**values)


def evidence(*variables):
    values = tuple(
        WeatherValue(
            variable=variable,
            value={
                WeatherVariable.TEMPERATURE_C: 8.0,
                WeatherVariable.RELATIVE_HUMIDITY_PERCENT: 60.0,
                WeatherVariable.WIND_SPEED_KMH: 10.0,
                WeatherVariable.CLOUD_COVER_PERCENT: 20.0,
            }[variable],
            unit={
                WeatherVariable.TEMPERATURE_C: "°C",
                WeatherVariable.RELATIVE_HUMIDITY_PERCENT: "%",
                WeatherVariable.WIND_SPEED_KMH: "km/h",
                WeatherVariable.CLOUD_COVER_PERCENT: "%",
            }[variable],
        )
        for variable in variables
    )
    if not values:
        return DecisionForecastEvidence(())
    return DecisionForecastEvidence(
        (
            WeatherForecastPoint(
                provider_id="provider",
                model_id="model",
                retrieved_at_utc=OBSERVED_AT - timedelta(hours=4),
                forecast_for_utc=OBSERVED_AT,
                requested_location=LOCATION,
                grid_location=LOCATION,
                values=values,
            ),
        )
    )


class MutableEvidenceStore:
    def __init__(self, value):
        self.value = value

    def load(self, *, decision_id):
        assert decision_id == "decision-1"
        return self.value


class ContextResolver:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def resolve(self, source):
        self.calls.append(source.observation_id)
        if self.error is not None:
            raise self.error
        return object()


class TickingClock:
    def __init__(self):
        self.values = iter((FIRST_COMPUTED_AT, SECOND_COMPUTED_AT))

    def __call__(self):
        return next(self.values)


def service(tmp_path, source, forecast, *, clock=None, outcome_store=None, resolver=None):
    observation_store = FileFieldObservationStore(tmp_path / "observations")
    observation_store.save(observation=source)
    return OutcomeEvaluationOrchestrationService(
        observation_store=observation_store,
        forecast_evidence_store=forecast,
        outcome_evaluation_store=(
            outcome_store
            if outcome_store is not None
            else FileOutcomeEvaluationStore(tmp_path / "outcomes")
        ),
        context_resolver=resolver or ContextResolver(),
        clock=clock or (lambda: FIRST_COMPUTED_AT),
    )


def test_decision_only_publishes_comparison_without_execution_artifacts(tmp_path):
    source = observation(execution_id=None)
    orchestration = service(
        tmp_path,
        source,
        MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C)),
    )

    result = orchestration.evaluate(source.observation_id)

    assert result.created is True
    assert result.evaluation.comparison.status is ForecastObservationComparisonStatus.COMPARABLE
    assert result.evaluation.outcome_evidence is None
    assert result.evaluation.assessment is None


@pytest.mark.parametrize(
    "conditions,forecast,comparison_status,assessment_status,bases",
    [
        (
            ObservedConditions(temperature_c=7.0),
            evidence(),
            ForecastObservationComparisonStatus.NOT_COMPARABLE,
            OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE,
            (),
        ),
        (
            ObservedConditions(
                temperature_c=7.0,
                relative_humidity_percent=55.0,
            ),
            evidence(WeatherVariable.TEMPERATURE_C),
            ForecastObservationComparisonStatus.PARTIAL,
            OutcomeAssessmentStatus.PARTIAL,
            ("forecast_observation.temperature_c.comparable",),
        ),
        (
            ObservedConditions(
                temperature_c=7.0,
                relative_humidity_percent=55.0,
            ),
            evidence(
                WeatherVariable.TEMPERATURE_C,
                WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
            ),
            ForecastObservationComparisonStatus.COMPARABLE,
            OutcomeAssessmentStatus.SUFFICIENT,
            (
                "forecast_observation.temperature_c.comparable",
                "forecast_observation.relative_humidity_percent.comparable",
            ),
        ),
    ],
)
def test_execution_mapping_findings_and_derived_evidence_are_exact(
    tmp_path,
    conditions,
    forecast,
    comparison_status,
    assessment_status,
    bases,
):
    orchestration = service(
        tmp_path,
        observation(conditions=conditions),
        MutableEvidenceStore(forecast),
    )

    evaluation = orchestration.evaluate("observation-1").evaluation

    assert evaluation.comparison.status is comparison_status
    assert evaluation.outcome_evidence.source_type is ForecastComparisonOutcomeEvidenceSourceType.SYSTEM_DERIVED
    assert evaluation.outcome_evidence.algorithm_version == "forecast_comparison_outcome_evidence.v1"
    assert evaluation.assessment.status is assessment_status
    assert tuple(item.basis for item in evaluation.assessment.findings) == bases
    assert all(
        item.evidence_ids == (evaluation.outcome_evidence.evidence_id,)
        for item in evaluation.assessment.findings
    )


def test_replay_returns_same_ids_and_canonical_timestamps(tmp_path):
    forecast = MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C))
    orchestration = service(
        tmp_path,
        observation(),
        forecast,
        clock=TickingClock(),
    )

    first = orchestration.evaluate("observation-1")
    replay = orchestration.evaluate("observation-1")

    assert first.created is True
    assert replay.created is False
    assert replay.evaluation == first.evaluation
    assert replay.evaluation.comparison.computed_at_utc == FIRST_COMPUTED_AT
    assert replay.evaluation.outcome_evidence.derived_at_utc == FIRST_COMPUTED_AT
    assert replay.evaluation.assessment.assessed_at == FIRST_COMPUTED_AT


def test_changed_input_for_same_observation_conflicts_without_second_publication(tmp_path):
    forecast = MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C))
    outcome_store = FileOutcomeEvaluationStore(tmp_path / "outcomes")
    orchestration = service(
        tmp_path,
        observation(),
        forecast,
        outcome_store=outcome_store,
    )
    orchestration.evaluate("observation-1")
    forecast.value = evidence(
        WeatherVariable.TEMPERATURE_C,
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
    )

    with pytest.raises(
        OutcomeEvaluationOrchestrationError,
        match="outcome_evaluation_conflict",
    ):
        orchestration.evaluate("observation-1")
    assert len(outcome_store.list_by_observation(observation_id="observation-1")) == 1


@pytest.mark.parametrize("document", [None, "not-json"])
def test_missing_or_corrupt_observation_never_publishes(tmp_path, document):
    observation_store = FileFieldObservationStore(tmp_path / "observations")
    if document is not None:
        (tmp_path / "observations").mkdir()
        (tmp_path / "observations" / "observation-1.json").write_text(document)
    outcome_store = FileOutcomeEvaluationStore(tmp_path / "outcomes")
    orchestration = OutcomeEvaluationOrchestrationService(
        observation_store=observation_store,
        forecast_evidence_store=MutableEvidenceStore(evidence()),
        outcome_evaluation_store=outcome_store,
        context_resolver=ContextResolver(),
        clock=lambda: FIRST_COMPUTED_AT,
    )

    with pytest.raises((FieldObservationPersistenceError, ValueError)):
        orchestration.evaluate("observation-1")
    assert outcome_store.list_by_observation(observation_id="observation-1") == []


def test_superseded_observation_is_rejected(tmp_path):
    source = observation()
    orchestration = service(
        tmp_path,
        source,
        MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C)),
    )
    orchestration.observation_store.save(
        observation=observation(
            observation_id="observation-2",
            supersedes_observation_id="observation-1",
        )
    )

    with pytest.raises(
        FieldObservationPersistenceError,
        match="field_observation_superseded",
    ):
        orchestration.evaluate("observation-1")


def test_fork_and_cycle_are_rejected_by_active_lease(tmp_path):
    directory = tmp_path / "observations"
    directory.mkdir()
    sources = (
        observation(),
        observation(
            observation_id="observation-2",
            supersedes_observation_id="observation-1",
        ),
        observation(
            observation_id="observation-3",
            supersedes_observation_id="observation-1",
        ),
    )
    for source in sources:
        (directory / f"{source.observation_id}.json").write_text(
            serialize_field_observation(source),
            encoding="utf-8",
        )
    store = FileFieldObservationStore(directory)
    with pytest.raises(
        FieldObservationPersistenceError,
        match="field_observation_supersession_ambiguous",
    ):
        with store.active_observation_lease(observation_id="observation-1"):
            pass

    (directory / "observation-3.json").unlink()
    cyclic = observation(
        observation_id="observation-1",
        supersedes_observation_id="observation-2",
    )
    (directory / "observation-1.json").write_text(
        serialize_field_observation(cyclic),
        encoding="utf-8",
    )
    with pytest.raises(
        FieldObservationPersistenceError,
        match="field_observation_supersession_corrupt",
    ):
        with store.active_observation_lease(observation_id="observation-1"):
            pass


def test_missing_and_corrupt_forecast_evidence_fail_closed(tmp_path):
    for value in (None, object()):
        case = tmp_path / ("missing" if value is None else "corrupt")
        outcome_store = FileOutcomeEvaluationStore(case / "outcomes")
        orchestration = service(
            case,
            observation(),
            MutableEvidenceStore(value),
            outcome_store=outcome_store,
        )
        with pytest.raises(ValueError):
            orchestration.evaluate("observation-1")
        assert outcome_store.list_by_observation(observation_id="observation-1") == []


def test_corrupt_persisted_forecast_error_propagates_without_publication(tmp_path):
    forecast_directory = tmp_path / "forecast"
    forecast_directory.mkdir()
    (forecast_directory / "decision-1.json").write_text(
        "not-json",
        encoding="utf-8",
    )
    outcome_store = FileOutcomeEvaluationStore(tmp_path / "outcomes")
    orchestration = service(
        tmp_path,
        observation(),
        FileDecisionForecastEvidenceStore(forecast_directory),
        outcome_store=outcome_store,
    )
    with pytest.raises(ValueError, match="invalid_json_document"):
        orchestration.evaluate("observation-1")
    assert outcome_store.list_by_observation(observation_id="observation-1") == []


def test_lineage_error_is_propagated_before_lease_or_publication(tmp_path):
    error = ValueError("execution_decision_mismatch")
    outcome_store = FileOutcomeEvaluationStore(tmp_path / "outcomes")
    orchestration = service(
        tmp_path,
        observation(),
        MutableEvidenceStore(evidence()),
        outcome_store=outcome_store,
        resolver=ContextResolver(error),
    )
    with pytest.raises(ValueError, match="execution_decision_mismatch"):
        orchestration.evaluate("observation-1")
    assert outcome_store.list_by_observation(observation_id="observation-1") == []


def test_non_persistable_comparison_is_rejected(monkeypatch, tmp_path):
    real_compare = orchestration_module.compare_forecast_to_field_observation

    def non_persistable(*args, **kwargs):
        return replace(
            real_compare(*args, **kwargs),
            identity_persistable=False,
        )

    monkeypatch.setattr(
        orchestration_module,
        "compare_forecast_to_field_observation",
        non_persistable,
    )
    orchestration = service(
        tmp_path,
        observation(),
        MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C)),
    )
    with pytest.raises(
        OutcomeEvaluationOrchestrationError,
        match="comparison_identity_not_persistable",
    ):
        orchestration.evaluate("observation-1")


def test_field_observation_lease_remains_held_through_outcome_save(tmp_path):
    source = observation()
    observation_store = FileFieldObservationStore(tmp_path / "observations")
    observation_store.save(observation=source)
    delegate = FileOutcomeEvaluationStore(tmp_path / "outcomes")
    entered_save = threading.Event()
    release_save = threading.Event()

    class BlockingOutcomeStore:
        def list_by_observation(self, **kwargs):
            return delegate.list_by_observation(**kwargs)

        def save(self, *, evaluation):
            entered_save.set()
            assert release_save.wait(5)
            return delegate.save(evaluation=evaluation)

    orchestration = OutcomeEvaluationOrchestrationService(
        observation_store=observation_store,
        forecast_evidence_store=MutableEvidenceStore(
            evidence(WeatherVariable.TEMPERATURE_C)
        ),
        outcome_evaluation_store=BlockingOutcomeStore(),
        context_resolver=ContextResolver(),
        clock=lambda: FIRST_COMPUTED_AT,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        evaluation_future = executor.submit(orchestration.evaluate, "observation-1")
        assert entered_save.wait(5)
        successor_future = executor.submit(
            observation_store.save,
            observation=observation(
                observation_id="observation-2",
                supersedes_observation_id="observation-1",
            ),
        )
        assert not successor_future.done()
        release_save.set()
        assert evaluation_future.result().created is True
        assert successor_future.result() is True


def test_apparent_failure_after_publication_is_recoverable_by_replay(tmp_path):
    delegate = FileOutcomeEvaluationStore(tmp_path / "outcomes")

    class PublishThenFailOnce:
        failed = False

        def list_by_observation(self, **kwargs):
            return delegate.list_by_observation(**kwargs)

        def save(self, *, evaluation):
            created = delegate.save(evaluation=evaluation)
            if not self.failed:
                self.failed = True
                raise OSError("unlock_failed")
            return created

    orchestration = service(
        tmp_path,
        observation(),
        MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C)),
        outcome_store=PublishThenFailOnce(),
        clock=TickingClock(),
    )
    with pytest.raises(OSError, match="unlock_failed"):
        orchestration.evaluate("observation-1")
    replay = orchestration.evaluate("observation-1")
    assert replay.created is False
    assert replay.evaluation.comparison.computed_at_utc == FIRST_COMPUTED_AT


def test_failure_before_publication_leaves_no_visible_aggregate(tmp_path):
    delegate = FileOutcomeEvaluationStore(tmp_path / "outcomes")

    class FailBeforePublish:
        def list_by_observation(self, **kwargs):
            return delegate.list_by_observation(**kwargs)

        def save(self, *, evaluation):
            raise OSError("write_failed")

    orchestration = service(
        tmp_path,
        observation(),
        MutableEvidenceStore(evidence(WeatherVariable.TEMPERATURE_C)),
        outcome_store=FailBeforePublish(),
    )
    with pytest.raises(OSError, match="write_failed"):
        orchestration.evaluate("observation-1")
    assert delegate.list_by_observation(observation_id="observation-1") == []


def test_orchestrator_has_no_forbidden_architecture_imports():
    source = Path(orchestration_module.__file__).read_text(encoding="utf-8")
    imported_modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
    forbidden = (
        "api",
        "ui",
        "scoring",
        "recommendation",
        "portfolio",
        "learning",
        "calibration",
    )
    assert not any(
        any(part in module.lower() for part in forbidden)
        for module in imported_modules
    )
