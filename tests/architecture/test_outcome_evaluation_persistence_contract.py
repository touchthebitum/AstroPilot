import json
import multiprocessing
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
from astropilot.durable_file_publication import (
    fsync_directory,
    remove_temporary_file_durably,
)
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
    ComparisonReason,
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


def _multiprocess_outcome_save(directory, document, results):
    source = deserialize_outcome_evaluation(document)
    try:
        results.put(FileOutcomeEvaluationStore(Path(directory)).save(evaluation=source))
    except Exception as error:
        results.put((type(error).__name__, str(error)))


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
    restored = deserialize_outcome_evaluation(document, evaluation_id=source.evaluation_id)
    assert restored == source
    assert serialize_outcome_evaluation(restored) == document
    payload = json.loads(document)
    assert payload["schema_version"] == 1
    assert payload["domain_version"] == DOMAIN_VERSION
    assert payload["outcome_evaluation"]["comparison"]["results"][0]["result_type"] == "numeric"
    assert payload["outcome_evaluation"]["comparison"]["results"][1]["result_type"] == "cloud"


def test_non_utc_assessment_round_trip_is_canonical_utc_and_equivalent():
    source = evaluation()
    offset_assessment = replace(
        source.assessment,
        assessed_at=datetime(
            2026,
            9,
            29,
            21,
            tzinfo=timezone(timedelta(hours=1)),
        ),
    )
    normalized = replace(source, assessment=offset_assessment)

    document = serialize_outcome_evaluation(normalized)
    restored = deserialize_outcome_evaluation(document)

    assert normalized.assessment.assessed_at == NOW
    assert normalized.assessment.assessed_at.tzinfo is timezone.utc
    assert restored == normalized
    assert '"assessed_at": "2026-09-29T20:00:00+00:00"' in document


def test_signed_zero_is_canonicalized_for_all_persisted_comparison_floats():
    source = evaluation(execution=False)
    numeric, cloud = source.comparison.results
    negative = replace(
        source,
        comparison=replace(
            source.comparison,
            results=(
                replace(
                    numeric,
                    forecast_value=-0.0,
                    observed_value=-0.0,
                    signed_error=-0.0,
                    absolute_error=-0.0,
                ),
                replace(cloud, forecast_coverage_percent=-0.0),
            ),
        ),
    )
    positive = replace(
        source,
        comparison=replace(
            source.comparison,
            results=(
                replace(
                    numeric,
                    forecast_value=0.0,
                    observed_value=0.0,
                    signed_error=0.0,
                    absolute_error=0.0,
                ),
                replace(cloud, forecast_coverage_percent=0.0),
            ),
        ),
    )

    assert negative == positive
    assert serialize_outcome_evaluation(negative) == serialize_outcome_evaluation(
        positive
    )
    assert "-0.0" not in serialize_outcome_evaluation(negative)


@pytest.mark.parametrize("status", [
    ForecastObservationComparisonStatus.PARTIAL,
    ForecastObservationComparisonStatus.NOT_COMPARABLE,
])
def test_partial_and_not_comparable_round_trip_with_reasons_and_missing_point(status):
    source = evaluation(execution=False)
    unavailable = ComparisonReason(
        code="forecast_value_unavailable",
        variable=WeatherVariable.CLOUD_COVER_PERCENT,
    )
    non_comparable_cloud = CloudVariableComparison(
        variable=WeatherVariable.CLOUD_COVER_PERCENT,
        status=VariableComparisonStatus.NOT_COMPARABLE,
        unit="%",
        reasons=(unavailable,),
    )
    results = (non_comparable_cloud,)
    if status is ForecastObservationComparisonStatus.PARTIAL:
        results = (source.comparison.results[0], non_comparable_cloud)
    updated_comparison = replace(
        source.comparison,
        results=results,
        status=status,
        reasons=(unavailable,),
    )
    updated = replace(
        source,
        evaluation_id=derive_outcome_evaluation_id(
            comparison_id=updated_comparison.comparison_id
        ),
        comparison=updated_comparison,
    )

    document = serialize_outcome_evaluation(updated)
    restored = deserialize_outcome_evaluation(document)

    assert restored == updated
    assert restored.comparison.results[-1].forecast_point is None
    assert restored.comparison.results[-1].reasons == (unavailable,)
    assert serialize_outcome_evaluation(restored) == document


def test_decision_only_store_round_trip(tmp_path):
    source = evaluation(execution=False)
    store = FileOutcomeEvaluationStore(tmp_path)

    assert store.save(evaluation=source) is True
    assert store.load(evaluation_id=source.evaluation_id) == source
    assert store.save(evaluation=source) is False


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


@pytest.mark.parametrize("mutation,code", [
    (lambda root: root["outcome_evaluation"].update(extra=True), "invalid_outcome_evaluation_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"].update(extra=True), "invalid_comparison_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"]["parameters"].update(extra=True), "invalid_parameter_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"]["parameters"]["temporal_policy"].update(extra=True), "invalid_temporal_policy_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"]["parameters"]["cloud_mapping_policy"].update(extra=True), "invalid_cloud_policy_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"]["observation_provenance"].update(extra=True), "invalid_observation_provenance_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"]["results"][0].update(extra=True), "invalid_result_fields"),
    (lambda root: root["outcome_evaluation"]["comparison"]["results"][0]["forecast_point"].update(extra=True), "invalid_forecast_point_fields"),
    (lambda root: root["outcome_evaluation"]["outcome_evidence"].update(extra=True), "invalid_outcome_evidence_fields"),
    (lambda root: root["outcome_evaluation"]["assessment"].update(extra=True), "invalid_assessment_fields"),
    (lambda root: root["outcome_evaluation"]["assessment"]["findings"][0].update(extra=True), "invalid_finding_fields"),
])
def test_unknown_fields_are_rejected_at_nested_levels(mutation, code):
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    mutation(payload)
    with pytest.raises(OutcomeEvaluationPersistenceError, match=code):
        deserialize_outcome_evaluation(json.dumps(payload))


def test_deserialized_non_persistable_identity_is_rejected():
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    payload["outcome_evaluation"]["comparison"]["identity_persistable"] = False
    with pytest.raises(
        OutcomeEvaluationPersistenceError,
        match="comparison_identity_not_persistable",
    ):
        deserialize_outcome_evaluation(json.dumps(payload))


@pytest.mark.parametrize("field_path", [
    ("results", 0, "forecast_value"),
    ("results", 0, "observed_value"),
    ("results", 0, "signed_error"),
    ("results", 0, "absolute_error"),
    ("results", 0, "forecast_point", "temporal_offset_us"),
    ("results", 1, "forecast_coverage_percent"),
    ("results", 1, "forecast_point", "temporal_offset_us"),
    ("parameters", "temporal_policy", "maximum_absolute_offset_us"),
    ("parameters", "cloud_mapping_policy", "boundaries_percent", 0),
])
def test_boolean_comparison_numbers_are_rejected(field_path):
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    target = payload["outcome_evaluation"]["comparison"]
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = True
    with pytest.raises(OutcomeEvaluationPersistenceError, match="invalid_"):
        deserialize_outcome_evaluation(json.dumps(payload))


@pytest.mark.parametrize("field_name", ["interpolation_enabled", "averaging_enabled"])
@pytest.mark.parametrize("value", [0, 1])
def test_persisted_temporal_policy_booleans_require_exact_bool(field_name, value):
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    payload["outcome_evaluation"]["comparison"]["parameters"][
        "temporal_policy"
    ][field_name] = value

    with pytest.raises(
        OutcomeEvaluationPersistenceError,
        match=f"^invalid_{field_name}$",
    ):
        deserialize_outcome_evaluation(json.dumps(payload))


@pytest.mark.parametrize(
    "field_name,value",
    [("decision_id", False), ("execution_id", 0)],
)
def test_persisted_comparison_ids_require_exact_strings(field_name, value):
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    payload["outcome_evaluation"]["comparison"][field_name] = value

    with pytest.raises(
        OutcomeEvaluationPersistenceError,
        match=f"^invalid_{field_name}$",
    ):
        deserialize_outcome_evaluation(json.dumps(payload))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_non_finite_numeric_documents_are_rejected(token):
    document = serialize_outcome_evaluation(evaluation())
    document = document.replace('"forecast_value": 7.0', f'"forecast_value": {token}')
    with pytest.raises(OutcomeEvaluationPersistenceError):
        deserialize_outcome_evaluation(document)


def test_huge_json_integer_is_rejected_as_the_field_persistence_error():
    document = serialize_outcome_evaluation(evaluation())
    huge_integer = "9" * 1000
    document = document.replace(
        '"forecast_value": 7.0',
        f'"forecast_value": {huge_integer}',
    )

    with pytest.raises(
        OutcomeEvaluationPersistenceError,
        match="^invalid_forecast_value$",
    ):
        deserialize_outcome_evaluation(document)


def test_listing_huge_json_integer_fails_closed_as_store_corruption(tmp_path):
    source = evaluation()
    path = tmp_path / f"{source.evaluation_id}.json"
    document = serialize_outcome_evaluation(source).replace(
        '"forecast_value": 7.0',
        f'"forecast_value": {"9" * 1000}',
    )
    path.write_text(document, encoding="utf-8")

    with pytest.raises(
        OutcomeEvaluationPersistenceError,
        match="^outcome_evaluation_corrupt$",
    ):
        FileOutcomeEvaluationStore(tmp_path).list_by_observation(
            observation_id=source.comparison.observation_id
        )


@pytest.mark.parametrize("value", [
    "2026-09-29T21:00:00+01:00",
    "2026-09-29T20:00:00Z",
    "2026-09-29T20:00:00",
])
@pytest.mark.parametrize("field_path", [
    ("comparison", "computed_at_utc"),
    ("comparison", "results", 0, "forecast_point", "retrieved_at_utc"),
    ("comparison", "results", 0, "forecast_point", "forecast_for_utc"),
    ("outcome_evidence", "derived_at_utc"),
    ("assessment", "assessed_at"),
])
def test_persisted_datetimes_require_canonical_utc_without_fold_aliases(
    value,
    field_path,
):
    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    target = payload["outcome_evaluation"]
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    with pytest.raises(OutcomeEvaluationPersistenceError, match="invalid_"):
        deserialize_outcome_evaluation(json.dumps(payload))


def test_uppercase_sha256_identifiers_are_rejected_uniformly(tmp_path):
    with pytest.raises(ValueError, match="invalid_comparison_id"):
        comparison(comparison_id="A" * 64)

    payload = json.loads(serialize_outcome_evaluation(evaluation()))
    payload["outcome_evaluation"]["comparison"]["comparison_id"] = "A" * 64
    with pytest.raises(OutcomeEvaluationPersistenceError, match="invalid_comparison_id"):
        deserialize_outcome_evaluation(json.dumps(payload))

    with pytest.raises(OutcomeEvaluationPersistenceError, match="invalid_comparison_id"):
        FileOutcomeEvaluationStore(tmp_path).list_by_comparison(
            comparison_id="A" * 64
        )


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


def test_multiprocess_identical_writers_use_interprocess_publication_lock(tmp_path):
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    document = serialize_outcome_evaluation(evaluation())
    processes = [
        context.Process(
            target=_multiprocess_outcome_save,
            args=(str(tmp_path), document, results),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0

    assert sorted(results.get(timeout=2) for _ in processes) == [False, True]
    assert FileOutcomeEvaluationStore(tmp_path).load(
        evaluation_id=evaluation().evaluation_id
    ) == evaluation()


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


class _FailingTemporary:
    def __init__(self, wrapped, operation):
        self._wrapped = wrapped
        self._operation = operation
        self.name = wrapped.name

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, *args):
        return self._wrapped.__exit__(*args)

    def write(self, document):
        if self._operation == "write":
            raise OSError("write failed")
        return self._wrapped.write(document)

    def flush(self):
        if self._operation == "flush":
            raise OSError("flush failed")
        return self._wrapped.flush()

    def fileno(self):
        return self._wrapped.fileno()


@pytest.mark.parametrize("operation", ["write", "flush"])
def test_temp_write_and_flush_failures_preserve_primary_error(
    tmp_path,
    monkeypatch,
    operation,
):
    real_temporary = tempfile.NamedTemporaryFile

    def failing_temporary(*args, **kwargs):
        return _FailingTemporary(real_temporary(*args, **kwargs), operation)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", failing_temporary)
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
    )

    with pytest.raises(OSError, match=f"{operation} failed"):
        FileOutcomeEvaluationStore(tmp_path).save(evaluation=evaluation())
    assert list(tmp_path.glob("*.json")) == []


def test_temp_fsync_failure_preserves_primary_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        os,
        "fsync",
        lambda *_: (_ for _ in ()).throw(OSError("temp fsync failed")),
    )
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    with pytest.raises(OSError, match="temp fsync failed"):
        FileOutcomeEvaluationStore(tmp_path).save(evaluation=evaluation())
    assert list(tmp_path.glob("*.json")) == []


def test_link_failure_is_not_masked_by_cleanup_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        os,
        "link",
        lambda *_: (_ for _ in ()).throw(OSError("link failed")),
    )
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    with pytest.raises(OSError, match="link failed"):
        FileOutcomeEvaluationStore(tmp_path).save(evaluation=evaluation())


def test_directory_fsync_failure_is_ambiguous_and_replay_is_idempotent(
    tmp_path,
    monkeypatch,
):
    import astropilot.outcome_evaluation_store as store_module

    source = evaluation()
    store = FileOutcomeEvaluationStore(tmp_path)
    fsync_calls = 0

    def fail_once(*_):
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            raise OSError("directory fsync failed")

    monkeypatch.setattr(store_module, "fsync_directory", fail_once)

    with pytest.raises(OSError, match="directory fsync failed"):
        store.save(evaluation=source)
    assert store.load(evaluation_id=source.evaluation_id) == source
    assert store.save(evaluation=source) is False
    assert fsync_calls == 3


def test_identical_file_exists_race_resynchronizes_directory(
    tmp_path,
    monkeypatch,
):
    import astropilot.outcome_evaluation_store as store_module

    source = evaluation()
    destination = tmp_path / f"{source.evaluation_id}.json"
    original_exists = Path.exists
    original_link = os.link
    fsync_calls = 0

    def hide_destination(path):
        if path == destination:
            return False
        return original_exists(path)

    def publish_then_report_race(temporary, path):
        original_link(temporary, path)
        raise FileExistsError(path)

    def record_fsync(*_):
        nonlocal fsync_calls
        fsync_calls += 1

    monkeypatch.setattr(Path, "exists", hide_destination)
    monkeypatch.setattr(os, "link", publish_then_report_race)
    monkeypatch.setattr(store_module, "fsync_directory", record_fsync)

    assert FileOutcomeEvaluationStore(tmp_path).save(evaluation=source) is False
    assert fsync_calls == 2


def test_temp_unlink_is_followed_by_second_directory_fsync(tmp_path, monkeypatch):
    import astropilot.outcome_evaluation_store as store_module

    events = []
    real_unlink = Path.unlink

    def record_unlink(path, *args, **kwargs):
        events.append("unlink")
        return real_unlink(path, *args, **kwargs)

    def record_fsync(*_):
        events.append("fsync")

    monkeypatch.setattr(Path, "unlink", record_unlink)
    monkeypatch.setattr(store_module, "fsync_directory", record_fsync)

    assert FileOutcomeEvaluationStore(tmp_path).save(evaluation=evaluation()) is True
    assert events == ["fsync", "unlink", "fsync"]


def test_second_directory_fsync_failure_keeps_final_and_replay_recovers(
    tmp_path,
    monkeypatch,
):
    import astropilot.outcome_evaluation_store as store_module

    source = evaluation()
    store = FileOutcomeEvaluationStore(tmp_path)
    calls = 0

    def fail_second(*_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("cleanup directory fsync failed")

    monkeypatch.setattr(store_module, "fsync_directory", fail_second)

    with pytest.raises(OSError, match="cleanup directory fsync failed"):
        store.save(evaluation=source)
    assert store.load(evaluation_id=source.evaluation_id) == source
    assert list(tmp_path.glob("*.tmp")) == []
    assert store.save(evaluation=source) is False
    assert calls == 3


def test_primary_error_is_preserved_over_cleanup_directory_fsync_failure(
    tmp_path,
    monkeypatch,
):
    import astropilot.outcome_evaluation_store as store_module

    monkeypatch.setattr(
        os,
        "link",
        lambda *_: (_ for _ in ()).throw(OSError("link failed")),
    )
    monkeypatch.setattr(
        store_module,
        "fsync_directory",
        lambda *_: (_ for _ in ()).throw(OSError("cleanup fsync failed")),
    )

    with pytest.raises(OSError, match="^link failed$"):
        FileOutcomeEvaluationStore(tmp_path).save(evaluation=evaluation())


def test_directory_fsync_failure_is_not_masked_by_cleanup_failure(
    tmp_path,
    monkeypatch,
):
    import astropilot.outcome_evaluation_store as store_module

    monkeypatch.setattr(
        store_module,
        "fsync_directory",
        lambda *_: (_ for _ in ()).throw(OSError("directory fsync failed")),
    )
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    with pytest.raises(OSError, match="directory fsync failed"):
        FileOutcomeEvaluationStore(tmp_path).save(evaluation=evaluation())


def test_store_directory_and_file_shape_errors_fail_closed(tmp_path):
    directory_as_file = tmp_path / "store-file"
    directory_as_file.write_text("occupied", encoding="utf-8")
    with pytest.raises(OSError):
        FileOutcomeEvaluationStore(directory_as_file).save(evaluation=evaluation())

    source = evaluation()
    destination = tmp_path / f"{source.evaluation_id}.json"
    destination.mkdir()
    with pytest.raises(OutcomeEvaluationPersistenceError, match="corrupt"):
        FileOutcomeEvaluationStore(tmp_path).load(evaluation_id=source.evaluation_id)


def test_directory_fsync_preserves_fsync_error_over_close_error(
    tmp_path,
    monkeypatch,
):
    import astropilot.durable_file_publication as publication

    monkeypatch.setattr(publication.os, "open", lambda *_: 123)
    monkeypatch.setattr(
        publication.os,
        "fsync",
        lambda *_: (_ for _ in ()).throw(OSError("fsync failed")),
    )
    monkeypatch.setattr(
        publication.os,
        "close",
        lambda *_: (_ for _ in ()).throw(OSError("close failed")),
    )
    with pytest.raises(OSError, match="fsync failed"):
        fsync_directory(tmp_path)


def test_directory_fsync_has_explicit_windows_fallback(tmp_path, monkeypatch):
    import astropilot.durable_file_publication as publication

    monkeypatch.setattr(publication.os, "name", "nt")
    monkeypatch.setattr(
        publication.os,
        "open",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not open")),
    )
    fsync_directory(tmp_path)


def test_temporary_cleanup_has_explicit_windows_fallback(tmp_path, monkeypatch):
    import astropilot.durable_file_publication as publication

    temporary = tmp_path / "publication.tmp"
    temporary.write_text("temporary", encoding="utf-8")
    monkeypatch.setattr(publication.os, "name", "nt")
    monkeypatch.setattr(
        publication.os,
        "open",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not open")),
    )

    remove_temporary_file_durably(
        temporary,
        tmp_path,
        primary_error=None,
    )

    assert not temporary.exists()


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
