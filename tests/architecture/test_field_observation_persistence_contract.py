import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from astropilot.field_observation_store import FileFieldObservationStore
from decision.field_observation import (
    CaptureMethod,
    CloudState,
    Confidence,
    FieldObservation,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
    QualityFlag,
    StopReason,
)
from decision.field_observation_persistence import (
    DOMAIN_VERSION,
    FieldObservationPersistenceError,
    deserialize_field_observation,
    serialize_field_observation,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)


def observation(**overrides):
    values = {
        "observation_id": "observation-123",
        "decision_id": "decision-123",
        "execution_id": "execution-123",
        "observed_at_utc": OBSERVED_AT,
        "recorded_at_utc": OBSERVED_AT + timedelta(minutes=2),
        "supersedes_observation_id": None,
        "conditions": ObservedConditions(
            temperature_c=12.4,
            relative_humidity_percent=63,
            cloud_state=CloudState.FEW,
        ),
        "acquisition": ObservedAcquisition(
            attempted_frames=20,
            usable_frames=17,
            stop_reason=StopReason.COMPLETED,
        ),
        "technical": ObservedTechnical(hfr=2.3, hfr_unit="px"),
        "provenance": ObservationProvenance(
            source_type=ObservationSourceType.USER,
            capture_method=CaptureMethod.MANUAL,
        ),
        "quality": ObservationQuality(confidence=Confidence.HIGH),
    }
    values.update(overrides)
    return FieldObservation(**values)


def test_v2_round_trip_is_strict_lossless_and_deterministic():
    source = observation()
    document = serialize_field_observation(source)
    payload = json.loads(document)
    assert payload["schema_version"] == 2
    assert payload["domain_version"] == DOMAIN_VERSION
    assert deserialize_field_observation(
        document, observation_id=source.observation_id
    ) == source
    assert serialize_field_observation(source) == document


def test_historical_v1_is_read_only_flagged_and_ineligible(tmp_path):
    legacy = {
        "schema_version": 1,
        "observation": {
            "observation_id": "legacy-1",
            "execution_id": "old-execution",
            "observed_at_utc": OBSERVED_AT.isoformat(),
            "cloud_condition": "overcast",
            "transparency": None,
            "seeing": None,
            "dew_detected": False,
        },
    }
    path = tmp_path / "legacy-1.json"
    original = json.dumps(legacy, indent=2)
    path.write_text(original, encoding="utf-8")
    restored = FileFieldObservationStore(tmp_path).load(
        observation_id="legacy-1"
    )
    assert restored.decision_id is None
    assert restored.legacy_lineage_incomplete is True
    assert restored.calibration_eligible is False
    assert QualityFlag.LEGACY_LINEAGE_INCOMPLETE in restored.quality.flags
    assert path.read_text(encoding="utf-8") == original
    with pytest.raises(
        FieldObservationPersistenceError,
        match="legacy_field_observation_read_only",
    ):
        serialize_field_observation(restored)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(unexpected=True),
        lambda payload: payload["observation"]["conditions"].update(unexpected=True),
        lambda payload: payload.update(domain_version="other"),
    ],
)
def test_v2_rejects_unknown_fields_and_wrong_domain_version(mutation):
    payload = json.loads(serialize_field_observation(observation()))
    mutation(payload)
    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            json.dumps(payload), observation_id="observation-123"
        )


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_numbers_are_rejected(constant):
    document = serialize_field_observation(observation()).replace("12.4", constant)
    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(document, observation_id="observation-123")


def test_create_only_replay_is_idempotent_and_changed_payload_conflicts(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    source = observation()
    assert store.save(observation=source) is True
    original = (tmp_path / "observation-123.json").read_bytes()
    assert store.save(observation=source) is False
    with pytest.raises(
        FieldObservationPersistenceError,
        match="field_observation_conflict",
    ):
        store.save(
            observation=replace(
                source,
                conditions=ObservedConditions(cloud_state=CloudState.OVERCAST),
            )
        )
    assert (tmp_path / "observation-123.json").read_bytes() == original


def test_concurrent_identical_writers_create_once_and_replay_once(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    source = observation()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: store.save(observation=source), range(2)))
    assert sorted(results) == [False, True]
    assert store.load(observation_id=source.observation_id) == source


def test_concurrent_different_payloads_never_overwrite(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    first = observation()
    second = replace(
        first,
        conditions=ObservedConditions(cloud_state=CloudState.OVERCAST),
    )

    def save(source):
        try:
            return store.save(observation=source)
        except FieldObservationPersistenceError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, (first, second)))
    assert results.count(True) == 1
    assert results.count("field_observation_conflict") == 1
    assert store.load(observation_id="observation-123") in (first, second)


def test_supersession_preserves_original_and_lists_deterministically(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    original = observation(
        observation_id="observation-a",
        observed_at_utc=OBSERVED_AT + timedelta(minutes=10),
        recorded_at_utc=OBSERVED_AT + timedelta(minutes=11),
    )
    correction = observation(
        observation_id="observation-b",
        observed_at_utc=OBSERVED_AT + timedelta(minutes=5),
        recorded_at_utc=OBSERVED_AT + timedelta(minutes=12),
        supersedes_observation_id="observation-a",
    )
    store.save(observation=original)
    store.save(observation=correction)
    assert store.load(observation_id="observation-a") == original
    assert store.list_by_decision(decision_id="decision-123") == [
        correction,
        original,
    ]
    assert store.list_by_execution(execution_id="execution-123") == [
        correction,
        original,
    ]


def test_supersession_requires_existing_observation_from_same_decision(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    with pytest.raises(
        FieldObservationPersistenceError,
        match="superseded_observation_missing",
    ):
        store.save(
            observation=observation(
                observation_id="correction",
                supersedes_observation_id="missing",
            )
        )
    store.save(observation=observation(observation_id="original"))
    with pytest.raises(
        FieldObservationPersistenceError,
        match="superseded_observation_decision_mismatch",
    ):
        store.save(
            observation=observation(
                observation_id="correction",
                decision_id="decision-other",
                supersedes_observation_id="original",
            )
        )
