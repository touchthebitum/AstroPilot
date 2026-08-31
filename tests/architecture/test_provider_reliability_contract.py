from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from decision.weather.provider_reliability import (
    ComparisonStatus,
    ObservationQualityStatus,
    WeatherForecastPoint,
    WeatherLocation,
    WeatherObservationPoint,
    WeatherValue,
    WeatherVariable,
    compare_forecast_to_observation,
)


RETRIEVED = datetime(2026, 8, 29, 18, tzinfo=timezone.utc)
FORECAST_FOR = datetime(2026, 8, 29, 22, tzinfo=timezone.utc)
SITE = WeatherLocation(46.7508, 6.5495)


def value(variable, number, *, aggregation_period=None):
    units = {
        WeatherVariable.CLOUD_COVER_PERCENT: "%",
        WeatherVariable.PRECIPITATION_MM: "mm",
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT: "%",
        WeatherVariable.VISIBILITY_M: "m",
        WeatherVariable.WIND_SPEED_KMH: "km/h",
        WeatherVariable.WIND_GUST_KMH: "km/h",
        WeatherVariable.TEMPERATURE_C: "°C",
        WeatherVariable.DEW_POINT_C: "°C",
    }
    return WeatherValue(
        variable,
        number,
        units[variable],
        aggregation_period=aggregation_period,
    )


def forecast(*values, forecast_for=FORECAST_FOR):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        model_id=None,
        retrieved_at_utc=RETRIEVED,
        forecast_for_utc=forecast_for,
        requested_location=SITE,
        grid_location=SITE,
        values=values
        or (
            value(WeatherVariable.CLOUD_COVER_PERCENT, 30),
            value(WeatherVariable.TEMPERATURE_C, 8),
        ),
    )


def observation(
    *values,
    observed_at=FORECAST_FOR,
    location=SITE,
    quality=ObservationQualityStatus.VALIDATED,
):
    return WeatherObservationPoint(
        source_id="station_reference",
        station_id="station_123",
        observed_at_utc=observed_at,
        location=location,
        values=values
        or (
            value(WeatherVariable.CLOUD_COVER_PERCENT, 20),
            value(WeatherVariable.TEMPERATURE_C, 10),
        ),
        quality_status=quality,
    )


def compare(candidate_forecast=None, candidate_observation=None, **overrides):
    return compare_forecast_to_observation(
        candidate_forecast or forecast(),
        candidate_observation or observation(),
        time_tolerance=overrides.get("time_tolerance", timedelta(minutes=30)),
        spatial_tolerance_km=overrides.get("spatial_tolerance_km", 5.0),
    )


def test_forecast_identity_horizon_and_instants_are_immutable_and_utc():
    zurich = ZoneInfo("Europe/Zurich")
    point = WeatherForecastPoint(
        provider_id=" open_meteo ",
        retrieved_at_utc=RETRIEVED.astimezone(zurich),
        forecast_for_utc=FORECAST_FOR.astimezone(zurich),
        requested_location=SITE,
        grid_location=SITE,
        values=(value(WeatherVariable.TEMPERATURE_C, 8),),
    )

    assert point.provider_id == "open_meteo"
    assert point.retrieved_at_utc.tzinfo is timezone.utc
    assert point.forecast_for_utc.tzinfo is timezone.utc
    assert point.horizon == timedelta(hours=4)
    with pytest.raises(FrozenInstanceError):
        point.provider_id = "changed"


def test_location_preserves_optional_finite_altitude_without_defaulting_to_zero():
    assert WeatherLocation(46.7508, 6.5495).altitude_m is None
    assert WeatherLocation(46.7508, 6.5495, altitude_m=1_245).altitude_m == 1245.0

    for invalid in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="invalid_altitude"):
            WeatherLocation(46.7508, 6.5495, altitude_m=invalid)


def test_observation_preserves_distinct_source_and_station_identities():
    point = WeatherObservationPoint(
        source_id=" meteoswiss ",
        station_id=" chaumont ",
        observed_at_utc=FORECAST_FOR,
        location=SITE,
        values=(value(WeatherVariable.TEMPERATURE_C, 8),),
        quality_status=ObservationQualityStatus.VALIDATED,
    )

    assert point.source_id == "meteoswiss"
    assert point.station_id == "chaumont"

    with pytest.raises(ValueError, match="invalid_station_id"):
        WeatherObservationPoint(
            source_id="meteoswiss",
            station_id=" ",
            observed_at_utc=FORECAST_FOR,
            location=SITE,
            values=(value(WeatherVariable.TEMPERATURE_C, 8),),
            quality_status=ObservationQualityStatus.VALIDATED,
        )


@pytest.mark.parametrize("quality_status", tuple(ObservationQualityStatus))
def test_observation_quality_states_are_explicitly_representable(quality_status):
    point = observation(
        value(WeatherVariable.TEMPERATURE_C, 8),
        quality=quality_status,
    )

    assert point.quality_status is quality_status


def test_observation_quality_status_is_required():
    with pytest.raises(TypeError):
        WeatherObservationPoint(
            source_id="meteoswiss",
            station_id="chaumont",
            observed_at_utc=FORECAST_FOR,
            location=SITE,
            values=(value(WeatherVariable.TEMPERATURE_C, 8),),
        )


@pytest.mark.parametrize("quality_status", ["validated", "unverified", "rejected"])
def test_observation_quality_status_rejects_raw_strings(quality_status):
    with pytest.raises(ValueError, match="invalid_observation_quality_status"):
        observation(
            value(WeatherVariable.TEMPERATURE_C, 8),
            quality=quality_status,
        )


def test_forecast_captured_after_its_valid_time_is_rejected():
    with pytest.raises(ValueError, match="forecast_captured_after_valid_time"):
        forecast(forecast_for=RETRIEVED - timedelta(seconds=1))


@pytest.mark.parametrize(
    ("variable", "valid_value"),
    [
        (WeatherVariable.CLOUD_COVER_PERCENT, 50),
        (WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 80),
        (WeatherVariable.VISIBILITY_M, 15_000),
        (WeatherVariable.WIND_SPEED_KMH, 12),
        (WeatherVariable.WIND_GUST_KMH, 20),
        (WeatherVariable.TEMPERATURE_C, 5),
        (WeatherVariable.DEW_POINT_C, 2),
    ],
)
def test_initial_instantaneous_variables_use_canonical_units(variable, valid_value):
    assert value(variable, valid_value).value == float(valid_value)


def test_precipitation_requires_an_explicit_aggregation_period():
    with pytest.raises(ValueError, match="precipitation_aggregation_period_required"):
        value(WeatherVariable.PRECIPITATION_MM, 1.2)

    measured = value(
        WeatherVariable.PRECIPITATION_MM,
        1.2,
        aggregation_period=timedelta(hours=1),
    )
    assert measured.aggregation_period == timedelta(hours=1)


@pytest.mark.parametrize(
    ("variable", "number", "message"),
    [
        (WeatherVariable.CLOUD_COVER_PERCENT, 101, "weather_value_out_of_range"),
        (WeatherVariable.TEMPERATURE_C, float("nan"), "non_finite_weather_value"),
    ],
)
def test_invalid_weather_values_are_rejected(variable, number, message):
    with pytest.raises(ValueError, match=message):
        value(variable, number)


def test_duplicate_variables_are_rejected():
    with pytest.raises(ValueError, match="duplicate_forecast_variable"):
        forecast(
            value(WeatherVariable.TEMPERATURE_C, 8),
            value(WeatherVariable.TEMPERATURE_C, 9),
        )


def test_comparable_values_preserve_signed_and_absolute_errors():
    verification = compare()

    assert verification.status is ComparisonStatus.COMPARABLE
    assert verification.horizon == timedelta(hours=4)
    assert verification.time_difference == timedelta(0)
    assert verification.distance_km == pytest.approx(0.0)
    assert verification.forecast_for_utc == FORECAST_FOR
    assert verification.requested_location == SITE
    assert verification.grid_location == SITE
    assert verification.reference_source_id == "station_reference"
    assert verification.station_id == "station_123"
    assert verification.altitude_difference_m is None
    assert verification.observed_at_utc == FORECAST_FOR
    assert verification.observation_location == SITE
    errors = {error.variable: error for error in verification.errors}
    assert errors[WeatherVariable.CLOUD_COVER_PERCENT].signed_error == 10.0
    assert errors[WeatherVariable.CLOUD_COVER_PERCENT].absolute_error == 10.0
    assert errors[WeatherVariable.TEMPERATURE_C].signed_error == -2.0
    assert errors[WeatherVariable.TEMPERATURE_C].absolute_error == 2.0


def test_altitude_difference_is_forecast_grid_minus_observation_and_not_a_gate():
    forecast_location = WeatherLocation(46.7508, 6.5495, altitude_m=1_250)
    observation_location = WeatherLocation(46.7508, 6.5495, altitude_m=500)
    candidate_forecast = WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED,
        forecast_for_utc=FORECAST_FOR,
        requested_location=forecast_location,
        grid_location=forecast_location,
        values=(value(WeatherVariable.TEMPERATURE_C, 8),),
    )

    verification = compare(
        candidate_forecast=candidate_forecast,
        candidate_observation=observation(
            value(WeatherVariable.TEMPERATURE_C, 10),
            location=observation_location,
        ),
    )

    assert verification.status is ComparisonStatus.COMPARABLE
    assert verification.altitude_difference_m == 750.0
    assert verification.reasons == ()


def test_altitude_difference_is_none_when_either_altitude_is_missing():
    forecast_location = WeatherLocation(46.7508, 6.5495, altitude_m=1_250)
    candidate_forecast = WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED,
        forecast_for_utc=FORECAST_FOR,
        requested_location=forecast_location,
        grid_location=forecast_location,
        values=(value(WeatherVariable.TEMPERATURE_C, 8),),
    )

    verification = compare(candidate_forecast=candidate_forecast)

    assert verification.status is ComparisonStatus.COMPARABLE
    assert verification.altitude_difference_m is None


def test_missing_variable_is_reported_without_becoming_zero():
    candidate_observation = observation(
        value(WeatherVariable.TEMPERATURE_C, 10),
    )

    verification = compare(candidate_observation=candidate_observation)

    assert verification.status is ComparisonStatus.COMPARABLE
    assert len(verification.errors) == 1
    assert verification.errors[0].variable is WeatherVariable.TEMPERATURE_C
    assert verification.unmatched_variables == (
        WeatherVariable.CLOUD_COVER_PERCENT,
    )


def test_no_common_variable_is_not_comparable():
    verification = compare(
        candidate_forecast=forecast(value(WeatherVariable.VISIBILITY_M, 20_000)),
        candidate_observation=observation(
            value(WeatherVariable.TEMPERATURE_C, 10)
        ),
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert verification.errors == ()
    assert verification.reasons == ("no_comparable_variables",)


def test_observation_outside_explicit_time_tolerance_is_not_comparable():
    verification = compare(
        candidate_observation=observation(
            observed_at=FORECAST_FOR + timedelta(minutes=31)
        ),
        time_tolerance=timedelta(minutes=30),
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert "observation_time_outside_tolerance" in verification.reasons


def test_observation_outside_explicit_spatial_tolerance_is_not_comparable():
    verification = compare(
        candidate_observation=observation(
            location=WeatherLocation(47.0, 7.0),
        ),
        spatial_tolerance_km=5.0,
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert "observation_location_outside_tolerance" in verification.reasons
    assert verification.distance_km > 5.0


def test_rejected_observation_is_never_used_for_error_measurement():
    verification = compare(
        candidate_observation=observation(
            quality=ObservationQualityStatus.REJECTED
        )
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert verification.errors == ()
    assert "observation_rejected" in verification.reasons


def test_unverified_observation_is_not_comparable_without_numeric_error():
    verification = compare(
        candidate_observation=observation(
            quality=ObservationQualityStatus.UNVERIFIED
        )
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert verification.reasons == ("observation_quality_unverified",)
    assert verification.errors == ()


def test_quality_reason_coexists_with_other_non_comparability_reasons():
    verification = compare(
        candidate_observation=observation(
            observed_at=FORECAST_FOR + timedelta(minutes=31),
            quality=ObservationQualityStatus.UNVERIFIED,
        ),
        time_tolerance=timedelta(minutes=30),
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert "observation_quality_unverified" in verification.reasons
    assert "observation_time_outside_tolerance" in verification.reasons
    assert verification.errors == ()


def test_precipitation_periods_must_match():
    predicted = value(
        WeatherVariable.PRECIPITATION_MM,
        1.2,
        aggregation_period=timedelta(hours=1),
    )
    observed = value(
        WeatherVariable.PRECIPITATION_MM,
        0.8,
        aggregation_period=timedelta(minutes=30),
    )

    verification = compare(
        candidate_forecast=forecast(predicted),
        candidate_observation=observation(observed),
    )

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert verification.reasons == (
        "aggregation_period_mismatch:precipitation_mm",
    )


@pytest.mark.parametrize(
    ("time_tolerance", "spatial_tolerance_km", "message"),
    [
        (timedelta(seconds=-1), 5.0, "invalid_time_tolerance"),
        (timedelta(minutes=30), -1.0, "invalid_spatial_tolerance"),
    ],
)
def test_comparison_tolerances_are_mandatory_and_validated(
    time_tolerance,
    spatial_tolerance_km,
    message,
):
    with pytest.raises(ValueError, match=message):
        compare_forecast_to_observation(
            forecast(),
            observation(),
            time_tolerance=time_tolerance,
            spatial_tolerance_km=spatial_tolerance_km,
        )
