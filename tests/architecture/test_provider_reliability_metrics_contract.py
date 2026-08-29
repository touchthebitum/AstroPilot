from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherObservationPoint,
    WeatherValue,
    WeatherVariable,
    compare_forecast_to_observation,
)
from decision.weather.provider_reliability_metrics import (
    EvidenceStatus,
    HorizonBucket,
    ReliabilityMetricsPolicy,
    build_provider_reliability_report,
)


VALID_AT = datetime(2026, 8, 29, 22, tzinfo=timezone.utc)
SITE = WeatherLocation(46.7508, 6.5495)


def weather_value(variable, value):
    units = {
        WeatherVariable.CLOUD_COVER_PERCENT: "%",
        WeatherVariable.TEMPERATURE_C: "°C",
        WeatherVariable.WIND_SPEED_KMH: "km/h",
    }
    return WeatherValue(variable, value, units[variable])


def verification(
    *,
    provider="provider_a",
    model=None,
    horizon=timedelta(hours=4),
    forecast_values=None,
    observation_values=None,
    observed_at=VALID_AT,
    observation_quality="validated",
):
    forecast_values = forecast_values or (
        weather_value(WeatherVariable.TEMPERATURE_C, 12),
    )
    observation_values = observation_values or (
        weather_value(WeatherVariable.TEMPERATURE_C, 10),
    )
    forecast = WeatherForecastPoint(
        provider_id=provider,
        model_id=model,
        retrieved_at_utc=VALID_AT - horizon,
        forecast_for_utc=VALID_AT,
        requested_location=SITE,
        grid_location=SITE,
        values=forecast_values,
    )
    observation = WeatherObservationPoint(
        source_id="reference_station",
        observed_at_utc=observed_at,
        location=SITE,
        values=observation_values,
        quality_status=observation_quality,
    )
    return compare_forecast_to_observation(
        forecast,
        observation,
        time_tolerance=timedelta(minutes=30),
        spatial_tolerance_km=5,
    )


def policy(minimum_sample_size=3):
    return ReliabilityMetricsPolicy(
        horizon_buckets=(
            HorizonBucket("0-6h", timedelta(0), timedelta(hours=6)),
            HorizonBucket("6-24h", timedelta(hours=6), timedelta(hours=24)),
            HorizonBucket("24h+", timedelta(hours=24), None),
        ),
        minimum_sample_size=minimum_sample_size,
    )


def test_policy_requires_explicit_contiguous_full_horizon_coverage():
    with pytest.raises(ValueError, match="horizon_buckets_must_start_at_zero"):
        ReliabilityMetricsPolicy(
            (HorizonBucket("later", timedelta(hours=1), None),),
            minimum_sample_size=1,
        )

    with pytest.raises(ValueError, match="horizon_buckets_must_be_contiguous"):
        ReliabilityMetricsPolicy(
            (
                HorizonBucket("first", timedelta(0), timedelta(hours=6)),
                HorizonBucket("later", timedelta(hours=7), None),
            ),
            minimum_sample_size=1,
        )

    with pytest.raises(ValueError, match="horizon_buckets_must_cover_all_horizons"):
        ReliabilityMetricsPolicy(
            (HorizonBucket("finite", timedelta(0), timedelta(hours=6)),),
            minimum_sample_size=1,
        )


@pytest.mark.parametrize("minimum", [0, -1, True, 1.5])
def test_policy_rejects_invalid_minimum_sample_size(minimum):
    with pytest.raises(ValueError, match="invalid_minimum_sample_size"):
        ReliabilityMetricsPolicy(
            (HorizonBucket("all", timedelta(0), None),),
            minimum_sample_size=minimum,
        )


def test_horizon_boundary_belongs_to_the_later_bucket():
    report = build_provider_reliability_report(
        (verification(horizon=timedelta(hours=6)),),
        policy=policy(minimum_sample_size=1),
    )

    assert report.coverage[0].horizon_bucket == "6-24h"
    assert report.variable_metrics[0].horizon_bucket == "6-24h"


def test_metrics_are_factual_and_keep_signed_error():
    samples = (
        verification(
            forecast_values=(weather_value(WeatherVariable.TEMPERATURE_C, 12),),
        ),
        verification(
            forecast_values=(weather_value(WeatherVariable.TEMPERATURE_C, 8),),
        ),
        verification(
            forecast_values=(weather_value(WeatherVariable.TEMPERATURE_C, 14),),
        ),
    )

    report = build_provider_reliability_report(samples, policy=policy())
    metrics = report.variable_metrics[0]

    assert metrics.sample_count == 3
    assert metrics.evidence_status is EvidenceStatus.ELIGIBLE
    assert metrics.mean_signed_error == pytest.approx(4 / 3)
    assert metrics.mean_absolute_error == pytest.approx(8 / 3)
    assert metrics.root_mean_squared_error == pytest.approx((24 / 3) ** 0.5)
    assert metrics.unit == "°C"


def test_too_few_samples_are_explicitly_insufficient():
    report = build_provider_reliability_report(
        (verification(), verification()),
        policy=policy(minimum_sample_size=3),
    )

    assert report.variable_metrics[0].sample_count == 2
    assert report.variable_metrics[0].evidence_status is EvidenceStatus.INSUFFICIENT


def test_provider_model_variable_and_horizon_are_never_mixed():
    samples = (
        verification(provider="provider_a", model="model_1"),
        verification(provider="provider_a", model="model_2"),
        verification(provider="provider_b", model="model_1"),
        verification(provider="provider_a", model="model_1", horizon=timedelta(hours=12)),
        verification(
            provider="provider_a",
            model="model_1",
            forecast_values=(weather_value(WeatherVariable.WIND_SPEED_KMH, 12),),
            observation_values=(weather_value(WeatherVariable.WIND_SPEED_KMH, 10),),
        ),
    )

    report = build_provider_reliability_report(
        samples,
        policy=policy(minimum_sample_size=1),
    )

    keys = {
        (item.provider_id, item.model_id, item.variable, item.horizon_bucket)
        for item in report.variable_metrics
    }
    assert len(keys) == 5


def test_not_comparable_samples_are_counted_but_never_used_as_zero_error():
    rejected = verification(observation_quality="rejected")
    valid = verification()

    report = build_provider_reliability_report(
        (rejected, valid),
        policy=policy(minimum_sample_size=2),
    )

    coverage = report.coverage[0]
    assert coverage.total_count == 2
    assert coverage.comparable_count == 1
    assert coverage.not_comparable_count == 1
    assert coverage.not_comparable_reasons == (("observation_rejected", 1),)
    assert report.variable_metrics[0].sample_count == 1
    assert report.variable_metrics[0].mean_absolute_error == 2
    assert report.variable_metrics[0].evidence_status is EvidenceStatus.INSUFFICIENT


def test_missing_variable_does_not_create_a_sample():
    sample = verification(
        forecast_values=(
            weather_value(WeatherVariable.TEMPERATURE_C, 12),
            weather_value(WeatherVariable.CLOUD_COVER_PERCENT, 50),
        ),
        observation_values=(weather_value(WeatherVariable.TEMPERATURE_C, 10),),
    )

    report = build_provider_reliability_report(
        (sample,),
        policy=policy(minimum_sample_size=1),
    )

    assert [item.variable for item in report.variable_metrics] == [
        WeatherVariable.TEMPERATURE_C
    ]


def test_empty_input_produces_an_empty_report_without_claims():
    report = build_provider_reliability_report((), policy=policy())

    assert report.coverage == ()
    assert report.variable_metrics == ()


def test_metrics_results_are_immutable():
    report = build_provider_reliability_report(
        (verification(),),
        policy=policy(minimum_sample_size=1),
    )

    with pytest.raises(FrozenInstanceError):
        report.variable_metrics[0].sample_count = 99


def test_policy_and_verifications_are_mandatory_and_typed():
    with pytest.raises(ValueError, match="reliability_metrics_policy_required"):
        build_provider_reliability_report((), policy=None)

    with pytest.raises(ValueError, match="invalid_forecast_verification"):
        build_provider_reliability_report((object(),), policy=policy())


def test_verification_preserves_provider_and_model_provenance():
    sample = verification(provider="provider_a", model="model_1")

    assert sample.provider_id == "provider_a"
    assert sample.model_id == "model_1"
