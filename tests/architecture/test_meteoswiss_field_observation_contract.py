from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from inspect import signature

import pytest

from decision.weather.meteoswiss_assets import (
    MeteoSwissGranularity,
    MeteoSwissObservationAsset,
    MeteoSwissProductFamily,
)
import decision.weather.meteoswiss_field_observation as orchestrator
from decision.weather.meteoswiss_field_observation import (
    MeteoSwissFieldObservationBatch,
    MeteoSwissFieldObservationError,
    build_meteoswiss_field_observations,
)
from decision.weather.meteoswiss_observation import (
    MeteoSwissObservationRecord,
    MeteoSwissStationMetadata,
)
from decision.weather.meteoswiss_quality import MeteoSwissObservationQuality
from decision.weather.provider_reliability import (
    ObservationQualityStatus,
    WeatherObservationPoint,
)


OBSERVED_AT = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)
CSV_TEXT = (
    "station_abbr;reference_timestamp;tre200s0;ure200s0;tde200s0;"
    "fu3010z0;fu3010z1;rre150z0\n"
    "ABO;31.08.2026 12:00;8.5;;;;;\n"
)
STATION = MeteoSwissStationMetadata(
    station_id="ABO",
    latitude=46.0,
    longitude=7.0,
    altitude_m=1_000.0,
)


def asset(station_id="abo"):
    return MeteoSwissObservationAsset(
        station_id=station_id,
        granularity=MeteoSwissGranularity.TEN_MINUTES,
        product_family=MeteoSwissProductFamily.NOW,
        href="https://data.geo.admin.ch/observation.csv",
        asset_key="ogd-smn_abo_t_now.csv",
        checksum="1220" + "00" * 32,
        asset_updated_at_utc=OBSERVED_AT,
    )


def record(minute=0):
    return MeteoSwissObservationRecord(
        observed_at_utc=OBSERVED_AT.replace(minute=minute),
        measurements={"tre200s0": 8.5},
    )


@pytest.mark.parametrize("station_id", ["ABO", "ab1", "abcd"])
def test_invalid_asset_identity_is_rejected_before_parsing(monkeypatch, station_id):
    def unexpected_parser(*args, **kwargs):
        pytest.fail("parser must not be called")

    monkeypatch.setattr(
        orchestrator,
        "parse_meteoswiss_observation_csv",
        unexpected_parser,
    )

    with pytest.raises(
        MeteoSwissFieldObservationError,
        match="^invalid_asset_station_id$",
    ):
        build_meteoswiss_field_observations(
            asset=asset(station_id),
            csv_text=CSV_TEXT,
            station=STATION,
        )


def test_station_mismatch_is_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "parse_meteoswiss_observation_csv",
        lambda *args, **kwargs: pytest.fail("parser must not be called"),
    )

    with pytest.raises(
        MeteoSwissFieldObservationError,
        match="^station_identity_mismatch$",
    ):
        build_meteoswiss_field_observations(
            asset=asset(),
            csv_text=CSV_TEXT,
            station=MeteoSwissStationMetadata("CDF", 46.0, 7.0, 1_000.0),
        )


def test_exact_parser_quality_and_mapping_contract_preserves_order(monkeypatch):
    records = (record(20), record(10), record(20))
    quality = MeteoSwissObservationQuality(
        status=ObservationQualityStatus.UNVERIFIED,
        reason="specific_quality_reason",
    )
    parser_calls = []
    quality_calls = []
    mapping_calls = []

    def parse(text, *, expected_station_id):
        parser_calls.append((text, expected_station_id))
        return records

    def determine(source_asset):
        quality_calls.append(source_asset)
        return quality

    def map_record(source_record, station, *, quality_status):
        mapping_calls.append((source_record, station, quality_status))
        return source_record

    monkeypatch.setattr(orchestrator, "parse_meteoswiss_observation_csv", parse)
    monkeypatch.setattr(
        orchestrator,
        "determine_meteoswiss_observation_quality",
        determine,
    )
    monkeypatch.setattr(orchestrator, "map_meteoswiss_observation", map_record)
    source_asset = asset()

    batch = build_meteoswiss_field_observations(
        asset=source_asset,
        csv_text=CSV_TEXT,
        station=STATION,
    )

    assert parser_calls == [(CSV_TEXT, "ABO")]
    assert quality_calls == [source_asset]
    assert mapping_calls == [
        (item, STATION, ObservationQualityStatus.UNVERIFIED) for item in records
    ]
    assert batch.observations == records
    assert batch.quality is quality
    assert batch.quality.reason == "specific_quality_reason"


def test_empty_parser_output_still_determines_quality_once(monkeypatch):
    calls = []
    quality = MeteoSwissObservationQuality(
        ObservationQualityStatus.UNVERIFIED,
        "empty_batch_quality",
    )
    monkeypatch.setattr(
        orchestrator,
        "parse_meteoswiss_observation_csv",
        lambda text, *, expected_station_id: (),
    )
    monkeypatch.setattr(
        orchestrator,
        "determine_meteoswiss_observation_quality",
        lambda source_asset: calls.append(source_asset) or quality,
    )
    monkeypatch.setattr(
        orchestrator,
        "map_meteoswiss_observation",
        lambda *args, **kwargs: pytest.fail("mapper must not be called"),
    )

    batch = build_meteoswiss_field_observations(
        asset=asset(),
        csv_text=CSV_TEXT,
        station=STATION,
    )

    assert batch.observations == ()
    assert batch.quality is quality
    assert len(calls) == 1


def test_mapping_failure_is_fail_fast_without_partial_batch(monkeypatch):
    records = (record(0), record(10), record(20))
    calls = []
    monkeypatch.setattr(
        orchestrator,
        "parse_meteoswiss_observation_csv",
        lambda text, *, expected_station_id: records,
    )
    monkeypatch.setattr(
        orchestrator,
        "determine_meteoswiss_observation_quality",
        lambda source_asset: MeteoSwissObservationQuality(
            ObservationQualityStatus.UNVERIFIED,
            "reason",
        ),
    )

    def fail_on_second(source_record, station, *, quality_status):
        calls.append(source_record)
        if source_record is records[1]:
            raise ValueError("mapping_failed")
        return source_record

    monkeypatch.setattr(orchestrator, "map_meteoswiss_observation", fail_on_second)

    with pytest.raises(ValueError, match="^mapping_failed$"):
        build_meteoswiss_field_observations(
            asset=asset(),
            csv_text=CSV_TEXT,
            station=STATION,
        )

    assert calls == list(records[:2])


def test_real_pipeline_returns_directly_usable_observation_and_is_deterministic():
    first = build_meteoswiss_field_observations(
        asset=asset(),
        csv_text=CSV_TEXT,
        station=STATION,
    )
    second = build_meteoswiss_field_observations(
        asset=asset(),
        csv_text=CSV_TEXT,
        station=STATION,
    )

    assert first == second
    assert isinstance(first.observations, tuple)
    assert len(first.observations) == 1
    assert isinstance(first.observations[0], WeatherObservationPoint)
    assert first.observations[0].station_id == "ABO"
    assert first.observations[0].observed_at_utc == OBSERVED_AT
    assert first.quality.reason == "meteoswiss_realtime_quality_unverified"


def test_result_is_frozen_and_api_has_no_clock_or_selection_inputs():
    batch = build_meteoswiss_field_observations(
        asset=asset(),
        csv_text=CSV_TEXT,
        station=STATION,
    )

    with pytest.raises(FrozenInstanceError):
        batch.observations = ()

    assert isinstance(batch, MeteoSwissFieldObservationBatch)
    assert tuple(signature(build_meteoswiss_field_observations).parameters) == (
        "asset",
        "csv_text",
        "station",
    )


def test_orchestrator_exposes_no_acquisition_or_comparison_dependency():
    assert not any("acquisition" in name for name in vars(orchestrator))
    assert not any("comparison" in name for name in vars(orchestrator))
