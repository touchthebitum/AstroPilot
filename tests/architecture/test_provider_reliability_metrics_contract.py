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
    ReliabilityReportScope,
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


def report_scope(**overrides):
    return ReliabilityReportScope(
        center=overrides.get("center", SITE),
        radius_km=overrides.get("radius_km", 5),
        starts_at_utc=overrides.get(
            "starts_at_utc", VALID_AT - timedelta(days=1)
        ),
        ends_at_utc=overrides.get("ends_at_utc", VALID_AT + timedelta(days=1)),
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
        scope=report_scope(),
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

    report = build_provider_reliability_report(
        samples, policy=policy(), scope=report_scope()
    )
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
        scope=report_scope(),
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
        scope=report_scope(),
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
        scope=report_scope(),
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
        scope=report_scope(),
    )

    assert [item.variable for item in report.variable_metrics] == [
        WeatherVariable.TEMPERATURE_C
    ]


def test_empty_input_produces_an_empty_report_without_claims():
    report = build_provider_reliability_report(
        (), policy=policy(), scope=report_scope()
    )

    assert report.coverage == ()
    assert report.variable_metrics == ()


def test_metrics_results_are_immutable():
    report = build_provider_reliability_report(
        (verification(),),
        policy=policy(minimum_sample_size=1),
        scope=report_scope(),
    )

    with pytest.raises(FrozenInstanceError):
        report.variable_metrics[0].sample_count = 99


def test_policy_and_verifications_are_mandatory_and_typed():
    with pytest.raises(ValueError, match="reliability_metrics_policy_required"):
        build_provider_reliability_report((), policy=None, scope=report_scope())

    with pytest.raises(ValueError, match="invalid_forecast_verification"):
        build_provider_reliability_report(
            (object(),), policy=policy(), scope=report_scope()
        )


def test_verification_preserves_provider_and_model_provenance():
    sample = verification(provider="provider_a", model="model_1")

    assert sample.provider_id == "provider_a"
    assert sample.model_id == "model_1"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"radius_km": -1}, "invalid_reliability_scope_radius"),
        (
            {"starts_at_utc": datetime(2026, 8, 29, 20)},
            "scope_starts_at_must_be_timezone_aware",
        ),
        (
            {
                "starts_at_utc": VALID_AT + timedelta(hours=1),
                "ends_at_utc": VALID_AT,
            },
            "invalid_reliability_scope_interval",
        ),
    ],
)
def test_report_scope_is_explicit_and_strictly_validated(overrides, message):
    with pytest.raises(ValueError, match=message):
        report_scope(**overrides)


def test_report_scope_is_mandatory():
    with pytest.raises(ValueError, match="reliability_report_scope_required"):
        build_provider_reliability_report(
            (verification(),), policy=policy(), scope=None
        )


def test_time_scope_boundaries_are_inclusive():
    samples = (verification(), verification(horizon=timedelta(hours=1)))
    scope = report_scope(starts_at_utc=VALID_AT, ends_at_utc=VALID_AT)

    report = build_provider_reliability_report(
        samples, policy=policy(minimum_sample_size=1), scope=scope
    )

    assert report.coverage[0].total_count == 2
    assert report.context_exclusions == ()


def test_out_of_period_verification_is_excluded_and_explained():
    scope = report_scope(
        starts_at_utc=VALID_AT + timedelta(seconds=1),
        ends_at_utc=VALID_AT + timedelta(days=1),
    )

    report = build_provider_reliability_report(
        (verification(),), policy=policy(), scope=scope
    )

    assert report.coverage == ()
    assert report.variable_metrics == ()
    assert report.context_exclusions[0].excluded_count == 1
    assert report.context_exclusions[0].reasons == (
        ("forecast_time_outside_report_scope", 1),
    )


def test_out_of_area_verification_is_excluded_and_explained():
    report = build_provider_reliability_report(
        (verification(),),
        policy=policy(),
        scope=report_scope(center=WeatherLocation(47.5, 8.5), radius_km=1),
    )

    assert report.coverage == ()
    assert report.context_exclusions[0].reasons == (
        ("requested_location_outside_report_scope", 1),
    )


def test_each_context_exclusion_reason_remains_visible():
    report = build_provider_reliability_report(
        (verification(),),
        policy=policy(),
        scope=report_scope(
            center=WeatherLocation(47.5, 8.5),
            radius_km=1,
            starts_at_utc=VALID_AT + timedelta(hours=1),
            ends_at_utc=VALID_AT + timedelta(hours=2),
        ),
    )

    assert report.context_exclusions[0].excluded_count == 1
    assert report.context_exclusions[0].reasons == (
        ("forecast_time_outside_report_scope", 1),
        ("requested_location_outside_report_scope", 1),
    )


def test_context_exclusions_are_separated_by_provider_and_model():
    samples = (
        verification(provider="provider_a", model="one"),
        verification(provider="provider_a", model="two"),
        verification(provider="provider_b", model="one"),
    )
    scope = report_scope(
        starts_at_utc=VALID_AT + timedelta(hours=1),
        ends_at_utc=VALID_AT + timedelta(hours=2),
    )

    report = build_provider_reliability_report(samples, policy=policy(), scope=scope)

    assert [
        (item.provider_id, item.model_id) for item in report.context_exclusions
    ] == [
        ("provider_a", "one"),
        ("provider_a", "two"),
        ("provider_b", "one"),
    ]
