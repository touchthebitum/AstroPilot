import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from astropilot.decision_forecast_evidence_store import (
    FileDecisionForecastEvidenceStore,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
    deserialize_decision_forecast_evidence,
    serialize_decision_forecast_evidence,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


RETRIEVED_AT = datetime(2026, 8, 31, 18, tzinfo=timezone.utc)


def value(variable, number, *, aggregation_period=None):
    units = {
        WeatherVariable.CLOUD_COVER_PERCENT: "%",
        WeatherVariable.PRECIPITATION_MM: "mm",
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT: "%",
        WeatherVariable.TEMPERATURE_C: "°C",
        WeatherVariable.WIND_SPEED_KMH: "km/h",
    }
    return WeatherValue(
        variable=variable,
        value=number,
        unit=units[variable],
        aggregation_period=aggregation_period,
    )


def point(
    *values,
    hour=21,
    provider="open_meteo",
    model_id=None,
    requested_altitude=None,
    grid_altitude=1_245.0,
):
    return WeatherForecastPoint(
        provider_id=provider,
        model_id=model_id,
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=RETRIEVED_AT.replace(hour=hour),
        requested_location=WeatherLocation(46.7508, 6.5495, requested_altitude),
        grid_location=WeatherLocation(46.75, 6.55, grid_altitude),
        values=values or (value(WeatherVariable.TEMPERATURE_C, 8.25),),
    )


def evidence():
    return DecisionForecastEvidence(
        (
            point(
                value(WeatherVariable.TEMPERATURE_C, 8.25),
                value(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 79.5),
                hour=20,
                model_id="best_match",
                requested_altitude=None,
            ),
            point(
                value(
                    WeatherVariable.WIND_SPEED_KMH,
                    12.5,
                    aggregation_period=timedelta(minutes=10),
                ),
                hour=22,
                model_id=None,
                requested_altitude=1_200.0,
                grid_altitude=None,
            ),
        )
    )


def document_for(source=None, decision_id="decision-123"):
    return serialize_decision_forecast_evidence(
        decision_id=decision_id,
        evidence=source if source is not None else evidence(),
    )


def test_serialization_round_trip_is_lossless_deterministic_and_ordered():
    source = evidence()

    first_document = document_for(source)
    second_document = document_for(source)
    restored = deserialize_decision_forecast_evidence(
        first_document,
        decision_id="decision-123",
    )

    assert first_document == second_document
    assert restored == source
    assert [item.forecast_for_utc for item in restored.forecast_points] == [
        item.forecast_for_utc for item in source.forecast_points
    ]
    assert restored.forecast_points[0].values == source.forecast_points[0].values
    assert restored.forecast_points[0].model_id == "best_match"
    assert restored.forecast_points[1].model_id is None
    assert restored.forecast_points[0].requested_location.altitude_m is None
    assert restored.forecast_points[1].grid_location.altitude_m is None
    assert (
        restored.forecast_points[1].values[0].aggregation_period
        == timedelta(minutes=10)
    )


def test_root_document_is_explicit_and_versioned():
    payload = json.loads(document_for())

    assert set(payload) == {"schema_version", "decision_id", "forecast_evidence"}
    assert payload["schema_version"] == 1
    assert payload["decision_id"] == "decision-123"
    assert isinstance(payload["forecast_evidence"]["forecast_points"], list)


def test_cloud_cover_evidence_round_trip_is_lossless_and_schema_v1():
    cloud_point = point(
        value(WeatherVariable.CLOUD_COVER_PERCENT, 37.25),
        hour=23,
        provider="Open-Meteo",
        model_id="best_match",
        requested_altitude=1_200.0,
        grid_altitude=1_245.0,
    )
    source = DecisionForecastEvidence((cloud_point,))
    document = document_for(source)

    restored = deserialize_decision_forecast_evidence(
        document,
        decision_id="decision-123",
    )
    payload = json.loads(document)

    assert payload["schema_version"] == 1
    assert restored == source
    restored_point = restored.forecast_points[0]
    assert restored_point.provider_id == "Open-Meteo"
    assert restored_point.model_id == "best_match"
    assert restored_point.retrieved_at_utc == RETRIEVED_AT
    assert restored_point.forecast_for_utc == RETRIEVED_AT.replace(hour=23)
    assert restored_point.requested_location == cloud_point.requested_location
    assert restored_point.grid_location == cloud_point.grid_location
    assert restored_point.values == (
        value(WeatherVariable.CLOUD_COVER_PERCENT, 37.25),
    )


def test_empty_evidence_round_trip_is_supported():
    source = DecisionForecastEvidence(())

    assert deserialize_decision_forecast_evidence(
        document_for(source),
        decision_id="decision-123",
    ) == source


@pytest.mark.parametrize("version", [None, "1", 2, True])
def test_missing_invalid_or_unknown_schema_version_is_rejected(version):
    payload = json.loads(document_for())
    if version is None:
        del payload["schema_version"]
    else:
        payload["schema_version"] = version

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_schema_version",
    ):
        deserialize_decision_forecast_evidence(
            json.dumps(payload),
            decision_id="decision-123",
        )


@pytest.mark.parametrize("document", ["{", "[]", "null"])
def test_invalid_json_or_root_shape_is_rejected(document):
    with pytest.raises(DecisionForecastEvidencePersistenceError):
        deserialize_decision_forecast_evidence(
            document,
            decision_id="decision-123",
        )


def test_unknown_fields_are_rejected_at_every_level():
    payload = json.loads(document_for())
    payload["forecast_evidence"]["forecast_points"][0]["unexpected"] = True

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_forecast_point_fields",
    ):
        deserialize_decision_forecast_evidence(
            json.dumps(payload),
            decision_id="decision-123",
        )


def test_unknown_weather_variable_is_rejected():
    payload = json.loads(document_for())
    payload["forecast_evidence"]["forecast_points"][0]["values"][0][
        "variable"
    ] = "future_variable"

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_weather_variable",
    ):
        deserialize_decision_forecast_evidence(
            json.dumps(payload),
            decision_id="decision-123",
        )


def test_invalid_or_naive_datetime_is_rejected():
    payload = json.loads(document_for())
    payload["forecast_evidence"]["forecast_points"][0][
        "forecast_for_utc"
    ] = "2026-08-31T20:00:00"

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_forecast_for_utc",
    ):
        deserialize_decision_forecast_evidence(
            json.dumps(payload),
            decision_id="decision-123",
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [("value", True), ("value", float("nan")), ("aggregation_period_us", True)],
)
def test_invalid_numeric_value_or_duration_is_rejected(field, invalid):
    payload = json.loads(document_for())
    payload["forecast_evidence"]["forecast_points"][0]["values"][0][field] = invalid

    with pytest.raises(DecisionForecastEvidencePersistenceError):
        deserialize_decision_forecast_evidence(
            json.dumps(payload),
            decision_id="decision-123",
        )


def test_decision_id_mismatch_is_rejected():
    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="decision_id_mismatch",
    ):
        deserialize_decision_forecast_evidence(
            document_for(decision_id="decision-one"),
            decision_id="decision-two",
        )


@pytest.mark.parametrize("decision_id", ["", "../escape", "nested/path", ".hidden"])
def test_unsafe_decision_id_is_rejected(decision_id):
    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_decision_id",
    ):
        document_for(decision_id=decision_id)


def test_store_missing_file_returns_none(tmp_path):
    store = FileDecisionForecastEvidenceStore(tmp_path)

    assert store.load(decision_id="missing-decision") is None


def test_store_round_trip_and_identical_resave_are_idempotent(tmp_path):
    store = FileDecisionForecastEvidenceStore(tmp_path)
    source = evidence()

    store.save(decision_id="decision-123", evidence=source)
    initial = (tmp_path / "decision-123.json").read_bytes()
    store.save(decision_id="decision-123", evidence=source)

    assert store.load(decision_id="decision-123") == source
    assert (tmp_path / "decision-123.json").read_bytes() == initial


def test_store_refuses_overwrite_with_different_evidence(tmp_path):
    store = FileDecisionForecastEvidenceStore(tmp_path)
    store.save(decision_id="decision-123", evidence=evidence())

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="decision_forecast_evidence_conflict",
    ):
        store.save(
            decision_id="decision-123",
            evidence=DecisionForecastEvidence((point(hour=23),)),
        )

    assert store.load(decision_id="decision-123") == evidence()


@pytest.mark.parametrize("corrupt_content", ["{", "[]", '{"schema_version": 2}'])
def test_present_corrupt_file_raises_instead_of_returning_none(
    tmp_path,
    corrupt_content,
):
    (tmp_path / "decision-123.json").write_text(corrupt_content, encoding="utf-8")
    store = FileDecisionForecastEvidenceStore(tmp_path)

    with pytest.raises(DecisionForecastEvidencePersistenceError):
        store.load(decision_id="decision-123")


def test_store_writes_complete_temp_file_then_atomically_replaces(
    tmp_path,
    monkeypatch,
):
    store = FileDecisionForecastEvidenceStore(tmp_path)
    replacements = []
    real_replace = os.replace

    def inspect_then_replace(source, destination):
        source_path = type(tmp_path)(source)
        destination_path = type(tmp_path)(destination)
        replacements.append(
            (
                source_path.parent,
                destination_path,
                source_path.read_text(encoding="utf-8"),
            )
        )
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", inspect_then_replace)

    store.save(decision_id="decision-123", evidence=evidence())

    assert len(replacements) == 1
    temp_parent, destination, complete_document = replacements[0]
    assert temp_parent == tmp_path
    assert destination == tmp_path / "decision-123.json"
    assert json.loads(complete_document)["decision_id"] == "decision-123"
    assert store.load(decision_id="decision-123") == evidence()
