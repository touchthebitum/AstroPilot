from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.field_validation_comparison import (
    compare_decision_forecast_evidence,
)
from decision.weather.meteoswiss_observation import (
    MeteoSwissObservationRecord,
    MeteoSwissStationMetadata,
    map_meteoswiss_observation,
)
from decision.weather.provider_reliability import (
    CANONICAL_UNITS,
    ComparisonStatus,
    ObservationQualityStatus,
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)
STATION = MeteoSwissStationMetadata(
    station_id="cha",
    latitude=47.0056,
    longitude=6.9587,
    altitude_m=1_136.0,
)
FULL_MEASUREMENTS = {
    "tre200s0": 8.5,
    "ure200s0": 72.0,
    "tde200s0": 3.5,
    "fu3010z0": 12.0,
    "fu3010z1": 20.0,
    "rre150z0": 0.4,
}


def record(measurements):
    return MeteoSwissObservationRecord(
        observed_at_utc=OBSERVED_AT,
        measurements=measurements,
    )


def test_maps_all_six_parameters_with_exact_provenance_and_temporal_semantics():
    observation = map_meteoswiss_observation(
        record(FULL_MEASUREMENTS),
        STATION,
        quality_status=ObservationQualityStatus.UNVERIFIED,
    )

    assert observation.source_id == "swissmetnet"
    assert observation.station_id == STATION.station_id
    assert observation.observed_at_utc == OBSERVED_AT
    assert observation.location == WeatherLocation(
        STATION.latitude,
        STATION.longitude,
        altitude_m=STATION.altitude_m,
    )
    assert observation.quality_status is ObservationQualityStatus.UNVERIFIED
    assert [
        (item.variable, item.value, item.unit, item.aggregation_period)
        for item in observation.values
    ] == [
        (WeatherVariable.TEMPERATURE_C, 8.5, "°C", None),
        (WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 72.0, "%", None),
        (WeatherVariable.DEW_POINT_C, 3.5, "°C", None),
        (
            WeatherVariable.WIND_SPEED_KMH,
            12.0,
            "km/h",
            timedelta(minutes=10),
        ),
        (
            WeatherVariable.WIND_GUST_KMH,
            20.0,
            "km/h",
            timedelta(minutes=10),
        ),
        (
            WeatherVariable.PRECIPITATION_MM,
            0.4,
            "mm",
            timedelta(minutes=10),
        ),
    ]


def test_missing_measurements_are_omitted_while_explicit_zero_is_preserved():
    observation = map_meteoswiss_observation(
        record(
            {
                "tre200s0": 0.0,
                "ure200s0": None,
                "tde200s0": None,
                "fu3010z0": None,
                "fu3010z1": None,
                "rre150z0": 0.0,
            }
        ),
        STATION,
        quality_status=ObservationQualityStatus.VALIDATED,
    )

    assert [(item.variable, item.value) for item in observation.values] == [
        (WeatherVariable.TEMPERATURE_C, 0.0),
        (WeatherVariable.PRECIPITATION_MM, 0.0),
    ]


def test_unknown_parameters_are_ignored_and_input_order_does_not_affect_output():
    measurements = {
        "fu3010z1": 20.0,
        "unsupported_parameter": 999.0,
        "tre200s0": 8.5,
        "ure200s0": 72.0,
    }
    original = deepcopy(measurements)
    reversed_measurements = dict(reversed(tuple(measurements.items())))

    first = map_meteoswiss_observation(
        record(measurements),
        STATION,
        quality_status=ObservationQualityStatus.VALIDATED,
    )
    second = map_meteoswiss_observation(
        record(reversed_measurements),
        STATION,
        quality_status=ObservationQualityStatus.VALIDATED,
    )

    assert first == second
    assert measurements == original
    assert [item.variable for item in first.values] == [
        WeatherVariable.TEMPERATURE_C,
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
        WeatherVariable.WIND_GUST_KMH,
    ]


def test_all_supported_measurements_missing_uses_domain_error_contract():
    with pytest.raises(ValueError, match="observation_values_required"):
        map_meteoswiss_observation(
            record({parameter: None for parameter in FULL_MEASUREMENTS}),
            STATION,
            quality_status=ObservationQualityStatus.VALIDATED,
        )


def test_invalid_supported_value_is_not_reinterpreted_as_missing():
    with pytest.raises(ValueError, match="weather_value_out_of_range"):
        map_meteoswiss_observation(
            record({"ure200s0": 101.0}),
            STATION,
            quality_status=ObservationQualityStatus.VALIDATED,
        )


def test_raw_quality_status_is_rejected_by_the_domain():
    with pytest.raises(ValueError, match="invalid_observation_quality_status"):
        map_meteoswiss_observation(
            record({"tre200s0": 8.5}),
            STATION,
            quality_status="validated",
        )


def test_source_specific_inputs_are_immutable():
    source_record = record(FULL_MEASUREMENTS)

    with pytest.raises(FrozenInstanceError):
        STATION.station_id = "changed"
    with pytest.raises(FrozenInstanceError):
        source_record.observed_at_utc = OBSERVED_AT + timedelta(minutes=10)


def test_mapped_observation_is_directly_usable_by_field_validation():
    observation = map_meteoswiss_observation(
        record({"tre200s0": 8.5}),
        STATION,
        quality_status=ObservationQualityStatus.VALIDATED,
    )
    location = WeatherLocation(
        STATION.latitude,
        STATION.longitude,
        altitude_m=STATION.altitude_m,
    )
    forecast = WeatherForecastPoint(
        provider_id="open_meteo",
        model_id=None,
        retrieved_at_utc=OBSERVED_AT - timedelta(hours=1),
        forecast_for_utc=OBSERVED_AT,
        requested_location=location,
        grid_location=location,
        values=(
            WeatherValue(
                variable=WeatherVariable.TEMPERATURE_C,
                value=7.5,
                unit=CANONICAL_UNITS[WeatherVariable.TEMPERATURE_C],
            ),
        ),
    )

    verifications = compare_decision_forecast_evidence(
        DecisionForecastEvidence((forecast,)),
        observation,
        time_tolerance=timedelta(minutes=10),
        spatial_tolerance_km=1.0,
    )

    assert len(verifications) == 1
    assert verifications[0].status is ComparisonStatus.COMPARABLE
    assert verifications[0].errors[0].signed_error == -1.0
