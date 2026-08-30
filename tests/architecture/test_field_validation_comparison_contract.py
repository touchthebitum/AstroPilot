from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

import decision.weather.field_validation_comparison as comparison_module
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.field_validation_comparison import (
    compare_decision_forecast_evidence,
)
from decision.weather.provider_reliability import (
    ComparisonStatus,
    WeatherForecastPoint,
    WeatherForecastVerification,
    WeatherLocation,
    WeatherObservationPoint,
    WeatherValue,
    WeatherVariable,
)


RETRIEVED = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)
VALID_AT = RETRIEVED + timedelta(hours=4)
SITE = WeatherLocation(46.7508, 6.5495, altitude_m=1_245)


def value(variable, number, *, aggregation_period=None):
    units = {
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


def forecast(*values, valid_at=VALID_AT, location=SITE):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        model_id=None,
        retrieved_at_utc=RETRIEVED,
        forecast_for_utc=valid_at,
        requested_location=location,
        grid_location=location,
        values=values,
    )


def observation(
    *values,
    observed_at=VALID_AT,
    location=SITE,
    quality="validated",
):
    return WeatherObservationPoint(
        source_id="meteoswiss",
        station_id="chaumont",
        observed_at_utc=observed_at,
        location=location,
        values=values,
        quality_status=quality,
    )


def compare(evidence, measured, **overrides):
    return compare_decision_forecast_evidence(
        evidence,
        measured,
        time_tolerance=overrides.get("time_tolerance", timedelta(minutes=30)),
        spatial_tolerance_km=overrides.get("spatial_tolerance_km", 5.0),
    )


def test_empty_evidence_has_no_elementary_comparison():
    measured = observation(value(WeatherVariable.TEMPERATURE_C, 8))

    assert compare(DecisionForecastEvidence(()), measured) == ()


def test_no_common_variable_has_no_elementary_comparison():
    evidence = DecisionForecastEvidence(
        (forecast(value(WeatherVariable.WIND_SPEED_KMH, 12)),)
    )
    measured = observation(value(WeatherVariable.TEMPERATURE_C, 8))

    assert compare(evidence, measured) == ()


def test_one_candidate_returns_exactly_one_authoritative_verification():
    evidence = DecisionForecastEvidence(
        (forecast(value(WeatherVariable.TEMPERATURE_C, 6)),)
    )
    measured = observation(value(WeatherVariable.TEMPERATURE_C, 8))

    verifications = compare(evidence, measured)

    assert len(verifications) == 1
    assert isinstance(verifications[0], WeatherForecastVerification)
    assert verifications[0].status is ComparisonStatus.COMPARABLE
    assert verifications[0].errors[0].signed_error == -2


def test_candidates_keep_order_and_exact_policy_arguments(monkeypatch):
    ignored = forecast(value(WeatherVariable.WIND_SPEED_KMH, 10))
    first = forecast(
        value(WeatherVariable.TEMPERATURE_C, 6),
        valid_at=VALID_AT + timedelta(hours=1),
    )
    second = forecast(
        value(WeatherVariable.TEMPERATURE_C, 7),
        valid_at=VALID_AT + timedelta(hours=2),
    )
    evidence = DecisionForecastEvidence((ignored, first, second))
    measured = observation(value(WeatherVariable.TEMPERATURE_C, 8))
    time_tolerance = timedelta(minutes=17)
    spatial_tolerance_km = 3.25
    calls = []
    produced = [object(), object()]

    def authoritative(forecast_point, observation_point, **kwargs):
        calls.append((forecast_point, observation_point, kwargs))
        return produced[len(calls) - 1]

    monkeypatch.setattr(
        comparison_module,
        "compare_forecast_to_observation",
        authoritative,
    )

    result = compare_decision_forecast_evidence(
        evidence,
        measured,
        time_tolerance=time_tolerance,
        spatial_tolerance_km=spatial_tolerance_km,
    )

    assert result == tuple(produced)
    assert calls == [
        (
            first,
            measured,
            {
                "time_tolerance": time_tolerance,
                "spatial_tolerance_km": spatial_tolerance_km,
            },
        ),
        (
            second,
            measured,
            {
                "time_tolerance": time_tolerance,
                "spatial_tolerance_km": spatial_tolerance_km,
            },
        ),
    ]


@pytest.mark.parametrize(
    ("measured", "time_tolerance", "spatial_tolerance_km", "reason"),
    [
        (
            observation(
                value(WeatherVariable.TEMPERATURE_C, 8),
                quality="rejected",
            ),
            timedelta(minutes=30),
            5.0,
            "observation_rejected",
        ),
        (
            observation(
                value(WeatherVariable.TEMPERATURE_C, 8),
                observed_at=VALID_AT + timedelta(minutes=31),
            ),
            timedelta(minutes=30),
            5.0,
            "observation_time_outside_tolerance",
        ),
        (
            observation(
                value(WeatherVariable.TEMPERATURE_C, 8),
                location=WeatherLocation(47.0, 7.0),
            ),
            timedelta(minutes=30),
            5.0,
            "observation_location_outside_tolerance",
        ),
    ],
)
def test_authoritative_not_comparable_results_remain_unchanged(
    measured,
    time_tolerance,
    spatial_tolerance_km,
    reason,
):
    evidence = DecisionForecastEvidence(
        (forecast(value(WeatherVariable.TEMPERATURE_C, 6)),)
    )

    verification = compare(
        evidence,
        measured,
        time_tolerance=time_tolerance,
        spatial_tolerance_km=spatial_tolerance_km,
    )[0]

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert reason in verification.reasons
    assert verification.errors == ()


def test_aggregation_mismatch_is_returned_without_reinterpretation():
    predicted = value(
        WeatherVariable.PRECIPITATION_MM,
        1.2,
        aggregation_period=timedelta(hours=1),
    )
    measured_value = value(
        WeatherVariable.PRECIPITATION_MM,
        0.8,
        aggregation_period=timedelta(minutes=30),
    )
    evidence = DecisionForecastEvidence((forecast(predicted),))

    verification = compare(evidence, observation(measured_value))[0]

    assert verification.status is ComparisonStatus.NOT_COMPARABLE
    assert verification.reasons == (
        "aggregation_period_mismatch:precipitation_mm",
    )
    assert verification.errors == ()


def test_inputs_are_not_mutated():
    evidence = DecisionForecastEvidence(
        (forecast(value(WeatherVariable.TEMPERATURE_C, 6)),)
    )
    measured = observation(value(WeatherVariable.TEMPERATURE_C, 8))
    evidence_before = deepcopy(evidence)
    observation_before = deepcopy(measured)

    compare(evidence, measured)

    assert evidence == evidence_before
    assert measured == observation_before
