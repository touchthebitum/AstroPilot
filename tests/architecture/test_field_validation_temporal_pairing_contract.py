from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
import decision.weather.field_validation_temporal_pairing as pairing_module
from decision.weather.field_validation_temporal_pairing import (
    FieldValidationTemporalPairingError,
    compare_decision_forecast_evidence_to_observations,
)
from decision.weather.provider_reliability import (
    ComparisonStatus,
    ObservationQualityStatus,
    WeatherForecastPoint,
    WeatherLocation,
    WeatherObservationPoint,
    WeatherValue,
    WeatherVariable,
)


RETRIEVED_AT = datetime(2026, 8, 31, 18, tzinfo=timezone.utc)
FORECAST_AT = datetime(2026, 8, 31, 21, tzinfo=timezone.utc)
SITE = WeatherLocation(46.75, 6.55, altitude_m=1_000)
DISTANT_SITE = WeatherLocation(47.25, 7.25, altitude_m=1_000)


def weather_value(variable, number, *, aggregation_period=None):
    units = {
        WeatherVariable.PRECIPITATION_MM: "mm",
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT: "%",
        WeatherVariable.TEMPERATURE_C: "°C",
        WeatherVariable.WIND_SPEED_KMH: "km/h",
    }
    return WeatherValue(
        variable,
        number,
        units[variable],
        aggregation_period=aggregation_period,
    )


def forecast(*values, valid_at=FORECAST_AT):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        model_id=None,
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=valid_at,
        requested_location=SITE,
        grid_location=SITE,
        values=values
        or (weather_value(WeatherVariable.TEMPERATURE_C, 8.0),),
    )


def observation(
    minute_offset,
    *values,
    quality=ObservationQualityStatus.VALIDATED,
    location=SITE,
    station_id="ABO",
):
    return WeatherObservationPoint(
        source_id="swissmetnet",
        station_id=station_id,
        observed_at_utc=FORECAST_AT + timedelta(minutes=minute_offset),
        location=location,
        values=values
        or (weather_value(WeatherVariable.TEMPERATURE_C, 7.0),),
        quality_status=quality,
    )


def compare(evidence, observations, *, time_tolerance=timedelta(minutes=30)):
    return compare_decision_forecast_evidence_to_observations(
        evidence,
        observations,
        time_tolerance=time_tolerance,
        spatial_tolerance_km=5.0,
    )


def test_simple_pair_calls_comparator_once_with_exact_arguments(monkeypatch):
    predicted = forecast()
    measured = observation(0)
    produced = object()
    calls = []

    def authoritative(forecast_point, observation_point, **kwargs):
        calls.append((forecast_point, observation_point, kwargs))
        return produced

    monkeypatch.setattr(
        pairing_module,
        "compare_forecast_to_observation",
        authoritative,
    )

    result = compare(
        DecisionForecastEvidence((predicted,)),
        (measured,),
        time_tolerance=timedelta(minutes=17),
    )

    assert result == (produced,)
    assert calls == [
        (
            predicted,
            measured,
            {
                "time_tolerance": timedelta(minutes=17),
                "spatial_tolerance_km": 5.0,
            },
        )
    ]


def test_nearest_compatible_observation_is_the_only_selected_candidate():
    measured = (observation(-20), observation(-5), observation(7))

    verifications = compare(DecisionForecastEvidence((forecast(),)), measured)

    assert len(verifications) == 1
    assert verifications[0].observed_at_utc == FORECAST_AT - timedelta(minutes=5)
    assert verifications[0].time_difference == timedelta(minutes=5)


def test_nearest_outside_tolerance_is_still_compared_and_explained():
    verifications = compare(
        DecisionForecastEvidence((forecast(),)),
        (observation(40), observation(50)),
        time_tolerance=timedelta(minutes=30),
    )

    assert len(verifications) == 1
    assert verifications[0].observed_at_utc == FORECAST_AT + timedelta(minutes=40)
    assert verifications[0].status is ComparisonStatus.NOT_COMPARABLE
    assert "observation_time_outside_tolerance" in verifications[0].reasons


def test_offset_exactly_at_tolerance_boundary_is_comparable():
    verification = compare(
        DecisionForecastEvidence((forecast(),)),
        (observation(30),),
        time_tolerance=timedelta(minutes=30),
    )[0]

    assert verification.time_difference == timedelta(minutes=30)
    assert verification.status is ComparisonStatus.COMPARABLE


@pytest.mark.parametrize(
    "candidates",
    [
        (observation(-5), observation(5)),
        (observation(0, station_id="ABO"), observation(0, station_id="CDF")),
    ],
)
def test_equal_nearest_offsets_fail_closed(candidates):
    with pytest.raises(
        FieldValidationTemporalPairingError,
        match="^ambiguous_nearest_observation$",
    ):
        compare(DecisionForecastEvidence((forecast(),)), candidates)


def test_forecasts_are_processed_once_and_result_order_follows_evidence():
    first = forecast(valid_at=FORECAST_AT + timedelta(minutes=20))
    second = forecast(valid_at=FORECAST_AT - timedelta(minutes=20))
    measured = (observation(-19), observation(19))

    verifications = compare(DecisionForecastEvidence((first, second)), measured)

    assert len(verifications) == 2
    assert [item.forecast_for_utc for item in verifications] == [
        first.forecast_for_utc,
        second.forecast_for_utc,
    ]
    assert [item.observed_at_utc for item in verifications] == [
        FORECAST_AT + timedelta(minutes=19),
        FORECAST_AT - timedelta(minutes=19),
    ]


def test_same_observation_can_be_reused_by_distinct_forecasts():
    temperature = forecast(weather_value(WeatherVariable.TEMPERATURE_C, 8.0))
    humidity = forecast(
        weather_value(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 70.0)
    )
    measured = observation(
        0,
        weather_value(WeatherVariable.TEMPERATURE_C, 7.0),
        weather_value(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 75.0),
    )

    verifications = compare(
        DecisionForecastEvidence((temperature, humidity)),
        (measured,),
    )

    assert len(verifications) == 2
    assert all(item.observed_at_utc == measured.observed_at_utc for item in verifications)


def test_forecast_without_any_common_variable_produces_no_verification():
    predicted = forecast(weather_value(WeatherVariable.WIND_SPEED_KMH, 10.0))

    assert compare(
        DecisionForecastEvidence((predicted,)),
        (observation(0),),
    ) == ()


def test_multivariable_forecast_is_paired_as_one_point():
    predicted = forecast(
        weather_value(WeatherVariable.TEMPERATURE_C, 8.0),
        weather_value(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 70.0),
    )
    nearest = observation(
        1,
        weather_value(WeatherVariable.TEMPERATURE_C, 7.0),
    )
    farther = observation(
        2,
        weather_value(WeatherVariable.TEMPERATURE_C, 6.0),
        weather_value(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 75.0),
    )

    verification = compare(
        DecisionForecastEvidence((predicted,)),
        (farther, nearest),
    )[0]

    assert verification.observed_at_utc == nearest.observed_at_utc
    assert [error.variable for error in verification.errors] == [
        WeatherVariable.TEMPERATURE_C
    ]
    assert verification.unmatched_variables == (
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
    )


def test_quality_is_delegated_and_does_not_change_nearest_selection():
    nearest = observation(-1, quality=ObservationQualityStatus.UNVERIFIED)
    farther = observation(2, quality=ObservationQualityStatus.VALIDATED)

    verification = compare(
        DecisionForecastEvidence((forecast(),)),
        (farther, nearest),
    )[0]

    assert verification.observed_at_utc == nearest.observed_at_utc
    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert "observation_quality_unverified" in verification.reasons


def test_distance_is_delegated_and_does_not_change_nearest_selection():
    nearest = observation(1, location=DISTANT_SITE)
    farther = observation(2, location=SITE)

    verification = compare(
        DecisionForecastEvidence((forecast(),)),
        (farther, nearest),
    )[0]

    assert verification.observed_at_utc == nearest.observed_at_utc
    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert "observation_location_outside_tolerance" in verification.reasons


def test_aggregation_is_delegated_and_does_not_change_nearest_selection():
    predicted = forecast(
        weather_value(
            WeatherVariable.PRECIPITATION_MM,
            1.0,
            aggregation_period=timedelta(hours=1),
        )
    )
    nearest = observation(
        1,
        weather_value(
            WeatherVariable.PRECIPITATION_MM,
            0.5,
            aggregation_period=timedelta(minutes=10),
        ),
    )
    farther = observation(
        2,
        weather_value(
            WeatherVariable.PRECIPITATION_MM,
            0.5,
            aggregation_period=timedelta(hours=1),
        ),
    )

    verification = compare(
        DecisionForecastEvidence((predicted,)),
        (farther, nearest),
    )[0]

    assert verification.observed_at_utc == nearest.observed_at_utc
    assert verification.reasons == (
        "aggregation_period_mismatch:precipitation_mm",
    )


def test_empty_evidence_and_empty_observations_return_empty_tuple():
    assert compare(DecisionForecastEvidence(()), (observation(0),)) == ()
    assert compare(DecisionForecastEvidence((forecast(),)), ()) == ()


def test_same_inputs_are_deterministic_and_never_create_double_sample():
    evidence = DecisionForecastEvidence((forecast(),))
    measured = (observation(-20), observation(-5), observation(7))

    first = compare(evidence, measured)
    second = compare(evidence, measured)

    assert first == second
    assert len(first) == 1


@pytest.mark.parametrize(
    ("time_tolerance", "spatial_tolerance_km", "message"),
    [
        (timedelta(seconds=-1), 5.0, "invalid_time_tolerance"),
        (timedelta(minutes=30), -1.0, "invalid_spatial_tolerance"),
        (timedelta(minutes=30), True, "invalid_spatial_tolerance"),
        (timedelta(minutes=30), float("inf"), "invalid_spatial_tolerance"),
    ],
)
def test_invalid_tolerances_are_rejected_even_without_comparisons(
    time_tolerance,
    spatial_tolerance_km,
    message,
):
    with pytest.raises(ValueError, match=f"^{message}$"):
        compare_decision_forecast_evidence_to_observations(
            DecisionForecastEvidence(()),
            (),
            time_tolerance=time_tolerance,
            spatial_tolerance_km=spatial_tolerance_km,
        )
