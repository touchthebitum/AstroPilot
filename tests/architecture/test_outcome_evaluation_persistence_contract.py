import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
from decision.field_observation import (
    CaptureMethod,
    CloudState,
    Confidence,
    ObservationSourceType,
    QualityFlag,
)
from decision.models.forecast_observation_comparison import (
    CloudComparisonOutcome,
    CloudVariableComparison,
    ForecastObservationComparison,
    ForecastObservationComparisonStatus,
    ForecastObservationParameters,
    ForecastPointProvenance,
    NumericVariableComparison,
    ObservationComparisonProvenance,
    VariableComparisonStatus,
)
from decision.models.outcome_assessment import (
    OutcomeAssessment,
    OutcomeAssessmentStatus,
    OutcomeFinding,
)
from decision.models.outcome_evaluation import (
    FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION,
    ForecastComparisonOutcomeEvidence,
    ForecastComparisonOutcomeEvidenceSourceType,
    OutcomeEvaluation,
    derive_forecast_comparison_outcome_evidence_id,
    derive_outcome_evaluation_id,
)
from decision.outcome_evaluation_persistence import (
    DOMAIN_VERSION,
    OutcomeEvaluationPersistenceError,
    deserialize_outcome_evaluation,
    serialize_outcome_evaluation,
)
from decision.weather.provider_reliability import WeatherVariable


NOW = datetime(2026, 9, 29, 20, tzinfo=timezone.utc)


def comparison(*, execution_id="execution-1", comparison_id="a" * 64, persistable=True):
    point = ForecastPointProvenance(
        provider_id="provider", model_id="model", retrieved_at_utc=NOW,
        forecast_for_utc=NOW + timedelta(minutes=10), temporal_offset=timedelta(minutes=5),
    )
    return ForecastObservationComparison(
        comparison_id=comparison_id, identity_persistable=persistable,
        computed_at_utc=NOW, decision_id="decision-1", observation_id="observation-1",
        execution_id=execution_id, source_digest="b" * 64,
        parameters=ForecastObservationParameters(),
        observation_provenance=ObservationComparisonProvenance(
            source_type=ObservationSourceType.WEATHER_STATION, source_id="station-1",
            capture_method=CaptureMethod.AUTOMATIC, confidence=Confidence.HIGH,
            quality_flags=(QualityFlag.SENSOR_UNCALIBRATED,),
        ),
        results=(
            NumericVariableComparison(
                variable=WeatherVariable.TEMPERATURE_C, status=VariableComparisonStatus.COMPARABLE,
                unit="°C", forecast_value=7.0, observed_value=5.0, signed_error=2.0,
                absolute_error=2.0, forecast_point=point,
            ),
            CloudVariableComparison(
                variable=WeatherVariable.CLOUD_COVER_PERCENT, status=VariableComparisonStatus.COMPARABLE,
                unit="%", forecast_coverage_percent=20.0, predicted_condition=CloudState.FEW,
                observed_condition=CloudState.CLEAR, outcome=CloudComparisonOutcome.MISMATCH,
                confusion_cell=(CloudState.FEW, CloudState.CLEAR), forecast_point=point,
            ),
        ),
        status=ForecastObservationComparisonStatus.COMPARABLE, reasons=(),
    )


def evaluation(*, execution=True, comparison_id="a" * 64, version="outcome_evaluation.v1", assessment_id="assessment-1"):
    source = comparison(execution_id="execution-1" if execution else None, comparison_id=comparison_id)
    evaluation_id = derive_outcome_evaluation_id(comparison_id=source.comparison_id, evaluation_algorithm_version=version)
    if not execution:
        return OutcomeEvaluation(evaluation_id=evaluation_id, comparison=source, outcome_evidence=None, assessment=None, evaluation_algorithm_version=version)
    evidence_id = derive_forecast_comparison_outcome_evidence_id(
        evaluation_id=evaluation_id, comparison_id=source.comparison_id,
        decision_id=source.decision_id, observation_id=source.observation_id,
        execution_id=source.execution_id,
        algorithm_version=FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION,
    )
    evidence = ForecastComparisonOutcomeEvidence(
        evidence_id=evidence_id, comparison_id=source.comparison_id,
        decision_id=source.decision_id, observation_id=source.observation_id,
        execution_id=source.execution_id,
        algorithm_version=FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION,
        derived_at_utc=NOW,
    )
    assessment = OutcomeAssessment(
        assessment_id=assessment_id, execution_id=source.execution_id,
        evidence_ids=(evidence_id,), assessed_at=NOW,
        status=OutcomeAssessmentStatus.SUFFICIENT,
        findings=(OutcomeFinding(finding_id="finding-1", basis="comparison", evidence_ids=(evidence_id,)),),
    )
    return OutcomeEvaluation(
        evaluation_id=evaluation_id, comparison=source, outcome_evidence=evidence,
        assessment=assessment, evaluation_algorithm_version=version,
    )


def test_decision_only_and_execution_invariants():
    assert evaluation(execution=False).outcome_evidence is None
    complete = evaluation()
    with pytest.raises(ValueError, match="requires_evidence_and_assessment"):
        replace(complete, outcome_evidence=None)
    with pytest.raises(ValueError, match="decision_only"):
        OutcomeEvaluation(
            evaluation_id=derive_outcome_evaluation_id(comparison_id=complete.comparison.comparison_id),
            comparison=replace(complete.comparison, execution_id=None),
            outcome_evidence=complete.outcome_evidence, assessment=complete.assessment,
        )


def test_non_persistable_comparison_is_rejected_by_model_serializer_and_store(tmp_path):
    source = object.__new__(OutcomeEvaluation)
    object.__setattr__(source, "evaluation_id", "c" * 64)
    object.__setattr__(source, "comparison", comparison(persistable=False))
    object.__setattr__(source, "outcome_evidence", None)
    object.__setattr__(source, "assessment", None)
    object.__setattr__(source, "evaluation_algorithm_version", "outcome_evaluation.v1")
    with pytest.raises(ValueError, match="comparison_identity_not_persistable"):
        OutcomeEvaluation.__post_init__(source)
    with pytest.raises(OutcomeEvaluationPersistenceError, match="comparison_identity_not_persistable"):
        serialize_outcome_evaluation(source)
    with pytest.raises(OutcomeEvaluationPersistenceError, match="comparison_identity_not_persistable"):
        FileOutcomeEvaluationStore(tmp_path).save(evaluation=source)


def test_full_numeric_cloud_round_trip_is_strict_and_lossless():
    source = evaluation()
    document = serialize_outcome_evaluation(source)
    assert deserialize_outcome_evaluation(document, evaluation_id=source.evaluation_id) == source
    payload = json.loads(document)
    assert payload["schema_version"] == 1
    assert payload["domain_version"] == DOMAIN_VERSION
    assert payload["outcome_evaluation"]["comparison"]["results"][0]["result_type"] == "numeric"
    assert payload["outcome_evaluation"]["comparison"]["results"][1]["result_type"] == "cloud"


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p.update(extra=True), "invalid_root_fields"),
    (lambda p: p.update(schema_version=2), "invalid_schema_version"),
    (lambda p: p.update(domain_version="future"), "invalid_domain_version"),
])
def test_unknown_fields_and_versions_are_rejected(mutation, code):
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    mutation(payload)
    with pytest.raises(OutcomeEvaluationPersistenceError, match=code):
        deserialize_outcome_evaluation(json.dumps(payload))


@pytest.mark.parametrize("document", ["{", "[]", "null"])
def test_invalid_json_is_rejected(document):
    with pytest.raises(OutcomeEvaluationPersistenceError):
        deserialize_outcome_evaluation(document)


def test_ids_change_with_algorithm_version_and_comparison_id():
    assert evaluation(version="outcome_evaluation.v1").evaluation_id != evaluation(version="outcome_evaluation.v2").evaluation_id
    assert evaluation(comparison_id="a" * 64).evaluation_id != evaluation(comparison_id="c" * 64).evaluation_id


def test_derived_evidence_contains_only_lineage_and_system_provenance():
    evidence = evaluation().outcome_evidence
    assert {item.name for item in fields(evidence)} == {
        "evidence_id", "comparison_id", "decision_id", "observation_id",
        "execution_id", "algorithm_version", "derived_at_utc", "source_type",
    }
    assert evidence.source_type is ForecastComparisonOutcomeEvidenceSourceType.SYSTEM_DERIVED


def test_store_replay_conflict_listing_and_corruption_fail_closed(tmp_path):
    store = FileOutcomeEvaluationStore(tmp_path)
    first = evaluation()
    second = evaluation(version="outcome_evaluation.v2", assessment_id="assessment-2")
    assert store.save(evaluation=second) is True
    assert store.save(evaluation=first) is True
    assert store.save(evaluation=first) is False
    assert store.list_by_observation(observation_id="observation-1") == sorted([first, second], key=lambda item: item.evaluation_id)
    assert store.list_by_execution(execution_id="execution-1") == sorted([first, second], key=lambda item: item.evaluation_id)
    assert store.list_by_comparison(comparison_id="a" * 64) == sorted([first, second], key=lambda item: item.evaluation_id)
    path = tmp_path / f"{first.evaluation_id}.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(OutcomeEvaluationPersistenceError, match="outcome_evaluation_corrupt"):
        store.list_by_observation(observation_id="observation-1")


def test_same_id_different_content_conflicts_without_overwrite(tmp_path):
    store = FileOutcomeEvaluationStore(tmp_path)
    source = evaluation()
    assert store.save(evaluation=source)
    original = (tmp_path / f"{source.evaluation_id}.json").read_bytes()
    divergent = replace(source, assessment=replace(source.assessment, assessment_id="different"))
    with pytest.raises(OutcomeEvaluationPersistenceError, match="outcome_evaluation_conflict"):
        store.save(evaluation=divergent)
    assert (tmp_path / f"{source.evaluation_id}.json").read_bytes() == original


def test_concurrent_identical_and_divergent_writers_are_create_only(tmp_path):
    source = evaluation()
    divergent = replace(source, assessment=replace(source.assessment, assessment_id="different"))
    store_a = FileOutcomeEvaluationStore(tmp_path)
    store_b = FileOutcomeEvaluationStore(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda store: store.save(evaluation=source), (store_a, store_b)))
    assert sorted(results) == [False, True]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store_a.save, evaluation=source), pool.submit(store_b.save, evaluation=divergent)]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except OutcomeEvaluationPersistenceError as error:
            outcomes.append(str(error))
    assert outcomes.count(False) == 1
    assert outcomes.count("outcome_evaluation_conflict") == 1
    assert store_a.load(evaluation_id=source.evaluation_id) == source


def test_link_failure_leaves_no_partial_destination_or_temp(tmp_path, monkeypatch):
    store = FileOutcomeEvaluationStore(tmp_path)
    monkeypatch.setattr(os, "link", lambda *_: (_ for _ in ()).throw(OSError("link failed")))
    with pytest.raises(OSError, match="link failed"):
        store.save(evaluation=evaluation())
    assert list(tmp_path.glob("*.json")) == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_temp_creation_failure_leaves_no_partial_destination(tmp_path, monkeypatch):
    store = FileOutcomeEvaluationStore(tmp_path)

    def fail_temp(*args, **kwargs):
        raise OSError("temp failed")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", fail_temp)
    with pytest.raises(OSError, match="temp failed"):
        store.save(evaluation=evaluation())
    assert list(tmp_path.glob("*.json")) == []


def test_cleanup_failure_never_removes_or_partially_writes_destination(
    tmp_path,
    monkeypatch,
):
    source = evaluation()
    store = FileOutcomeEvaluationStore(tmp_path)
    real_unlink = Path.unlink

    def fail_temp_cleanup(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise OSError("cleanup failed")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_temp_cleanup)
    with pytest.raises(OSError, match="cleanup failed"):
        store.save(evaluation=source)
    assert store.load(evaluation_id=source.evaluation_id) == source


def test_architecture_boundary_uses_no_forbidden_imports():
    paths = [
        "decision/models/outcome_evaluation.py",
        "decision/outcome_evaluation_persistence.py",
        "astropilot/outcome_evaluation_store.py",
    ]
    forbidden = ("scoring", "recommendation", "portfolio", "learning", "calibration", "fastapi", "astropilot.app")
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        assert not any(f"import {name}" in source or f"from {name}" in source for name in forbidden)
