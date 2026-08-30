from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from decision.weather.provider_reliability import (
    ComparisonStatus,
    WeatherForecastVerification,
    WeatherLocation,
    WeatherVariable,
    WeatherVariableError,
)
from decision.weather.provider_reliability_metrics import (
    EvidenceStatus,
    HorizonBucket,
    ReliabilityMetricsPolicy,
    ReliabilityReportScope,
    build_provider_reliability_report,
)
from decision.weather.weather_ingress import WeatherFreshness, WeatherSnapshot
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherDecisionContext,
    WeatherEvidenceQuality,
    WeatherTrustDecisionEvaluator,
    WeatherTrustEvidence,
)


NOW = datetime(2026, 8, 30, 20, tzinfo=timezone.utc)
SITE = WeatherLocation(46.7508, 6.5495)


def reliability_scope(**overrides):
    values = {
        "center": SITE,
        "radius_km": 5,
        "starts_at_utc": NOW - timedelta(days=1),
        "ends_at_utc": NOW + timedelta(days=1),
    }
    values.update(overrides)
    return ReliabilityReportScope(**values)


def snapshot(**overrides):
    values = {
        "payload": {},
        "provider": "provider_a",
        "retrieved_at_utc": NOW - timedelta(minutes=5),
        "requested_latitude": SITE.latitude,
        "requested_longitude": SITE.longitude,
        "grid_latitude": SITE.latitude,
        "grid_longitude": SITE.longitude,
        "grid_distance_km": 0.0,
        "elevation_m": None,
        "timezone": "Europe/Zurich",
        "timezone_source": "coordinates_local",
        "utc_offset_seconds": 7200,
        "valid_from": NOW,
        "valid_until": NOW + timedelta(hours=12),
        "hour_count": 24,
        "completeness": 1.0,
    }
    values.update(overrides)
    return WeatherSnapshot(**values)


def verification(*, maximum_error=2.0, reference="station_a"):
    error = WeatherVariableError(
        variable=WeatherVariable.CLOUD_COVER_PERCENT,
        forecast_value=20.0 + maximum_error,
        observed_value=20.0,
        unit="%",
        signed_error=maximum_error,
        absolute_error=maximum_error,
    )
    return WeatherForecastVerification(
        provider_id="provider_a",
        reference_source_id=reference,
        model_id="model_1",
        status=ComparisonStatus.COMPARABLE,
        horizon=timedelta(hours=6),
        time_difference=timedelta(0),
        distance_km=0.0,
        forecast_for_utc=NOW,
        requested_location=SITE,
        grid_location=SITE,
        observed_at_utc=NOW,
        observation_location=SITE,
        errors=(error,),
    )


def report(*verifications, minimum_sample_size=1):
    return build_provider_reliability_report(
        tuple(verifications),
        policy=ReliabilityMetricsPolicy(
            horizon_buckets=(HorizonBucket("all", timedelta(0), None),),
            minimum_sample_size=minimum_sample_size,
        ),
        scope=reliability_scope(),
    )


def context(**overrides):
    values = {
        "provider_id": "provider_a",
        "model_id": "model_1",
        "reference_source_id": "station_a",
        "horizon_bucket": "all",
        "required_variables": (WeatherVariable.CLOUD_COVER_PERCENT,),
        "reliability_scope": reliability_scope(),
        "decision_location": SITE,
    }
    values.update(overrides)
    return WeatherDecisionContext(**values)


def evidence(**overrides):
    values = {
        "snapshot": snapshot(),
        "freshness": WeatherFreshness(5.0, "fresh", 90),
        "selected_window_covered": True,
        "provider_reliability": report(verification()),
    }
    values.update(overrides)
    return WeatherTrustEvidence(**values)


def test_complete_eligible_evidence_is_admissible_without_a_trust_score():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.SUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.ADMISSIBLE
    assert not hasattr(decision, "score")


def test_unknown_provider_reliability_requires_caution_not_trust():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=None),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.CAUTION
    assert "provider_reliability_unavailable" in decision.reasons


def test_incoherent_freshness_cannot_produce_admissible():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(freshness=WeatherFreshness(5.0, "stale", 90)),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert "weather_not_fresh" in decision.reasons


def test_snapshot_location_must_match_the_decision_location():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(
            snapshot=snapshot(
                requested_latitude=47.3769,
                requested_longitude=8.5417,
            )
        ),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INVALID
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert "weather_location_mismatch" in decision.reasons


def test_snapshot_provider_mismatch_is_invalid_and_refused():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(snapshot=snapshot(provider="provider_b")),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INVALID
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert "weather_provider_mismatch" in decision.reasons


def test_too_few_observations_cannot_be_promoted_to_sufficient():
    insufficient = report(verification(), minimum_sample_size=2)

    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=insufficient),
        context=context(),
    )

    assert (
        insufficient.variable_metrics[0].evidence_status
        is EvidenceStatus.INSUFFICIENT
    )
    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.CAUTION
    assert "provider_evidence_insufficient:cloud_cover_percent" in decision.reasons


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"snapshot": None}, "weather_snapshot_missing"),
        ({"freshness": None}, "weather_freshness_missing"),
        ({"selected_window_covered": False}, "selected_window_uncovered"),
    ],
)
def test_missing_required_current_evidence_refuses_the_decision(overrides, reason):
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(**overrides),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert reason in decision.reasons


def test_explicit_invalid_evidence_has_fail_closed_priority():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(
            provider_reliability=None,
            integrity_issues=("invalid_weather_units",),
        ),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INVALID
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert decision.reasons[0] == "invalid_weather_units"


def test_invalidity_has_priority_over_all_missing_operational_evidence():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        WeatherTrustEvidence(
            snapshot=None,
            freshness=None,
            selected_window_covered=None,
            provider_reliability=None,
            integrity_issues=("invalid_weather_units",),
        ),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INVALID
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert decision.reasons == ("invalid_weather_units",)


def test_unknown_selected_window_coverage_is_explicitly_refused():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(selected_window_covered=None),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.REFUSED
    assert "selected_window_coverage_unknown" in decision.reasons


def test_context_mismatch_is_explicit_and_never_uses_another_source():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(),
        context=context(reference_source_id="station_b"),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.CAUTION
    assert "provider_context_not_evaluated" in decision.reasons


def test_location_or_period_scope_mismatch_is_never_silently_mixed():
    other_period = reliability_scope(
        starts_at_utc=NOW - timedelta(days=10),
        ends_at_utc=NOW - timedelta(days=2),
    )

    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(),
        context=context(reliability_scope=other_period),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.CAUTION
    assert decision.reasons == ("provider_report_scope_mismatch",)


def test_required_variable_must_have_eligible_evidence():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(),
        context=context(required_variables=(WeatherVariable.WIND_SPEED_KMH,)),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert "provider_evidence_missing:wind_speed_kmh" in decision.reasons


def test_empty_provider_report_is_insufficient_and_requires_caution():
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=report()),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.CAUTION
    assert "provider_context_not_evaluated" in decision.reasons
    assert "provider_evidence_missing:cloud_cover_percent" in decision.reasons


def test_eligible_metrics_survive_visible_historical_exclusions():
    excluded = replace(
        verification(),
        requested_location=WeatherLocation(48.8566, 2.3522),
    )
    reliability = report(verification(), excluded)

    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=reliability),
        context=context(),
    )

    assert decision.evidence_quality is WeatherEvidenceQuality.SUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.ADMISSIBLE
    assert (
        "provider_context_excluded:requested_location_outside_report_scope"
        in decision.reasons
    )


def test_rejected_observation_never_creates_a_zero_error_or_positive_claim():
    rejected = replace(
        verification(),
        status=ComparisonStatus.NOT_COMPARABLE,
        errors=(),
        reasons=("observation_rejected",),
    )
    reliability = report(rejected)

    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=reliability),
        context=context(),
    )

    assert reliability.variable_metrics == ()
    assert decision.evidence_quality is WeatherEvidenceQuality.INSUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.CAUTION
    assert "provider_comparison_excluded:observation_rejected" in decision.reasons


def test_required_variable_order_does_not_change_the_decision():
    wind_error = WeatherVariableError(
        variable=WeatherVariable.WIND_SPEED_KMH,
        forecast_value=12.0,
        observed_value=10.0,
        unit="km/h",
        signed_error=2.0,
        absolute_error=2.0,
    )
    source = verification()
    reliability = report(replace(source, errors=(*source.errors, wind_error)))
    variables = (
        WeatherVariable.CLOUD_COVER_PERCENT,
        WeatherVariable.WIND_SPEED_KMH,
    )

    first = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=reliability),
        context=context(required_variables=variables),
    )
    second = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=reliability),
        context=context(required_variables=tuple(reversed(variables))),
    )

    assert first == second


def test_integrity_issue_order_does_not_change_the_decision():
    first = WeatherTrustDecisionEvaluator.evaluate(
        evidence(integrity_issues=("invalid_units", "invalid_timezone")),
        context=context(),
    )
    second = WeatherTrustDecisionEvaluator.evaluate(
        evidence(integrity_issues=("invalid_timezone", "invalid_units")),
        context=context(),
    )

    assert first == second


def test_extreme_error_remains_observable_without_becoming_a_hidden_average():
    reliability = report(verification(maximum_error=80.0))

    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=reliability),
        context=context(),
    )

    assert reliability.variable_metrics[0].maximum_absolute_error == 80.0
    assert "maximum_absolute_error:cloud_cover_percent:80" in decision.reasons
    assert decision.evidence_quality is WeatherEvidenceQuality.SUFFICIENT
    assert decision.admissibility is WeatherDecisionAdmissibility.ADMISSIBLE


def test_contract_is_immutable_and_does_not_modify_input_reports():
    reliability = report(verification())
    before = reliability.variable_metrics
    decision = WeatherTrustDecisionEvaluator.evaluate(
        evidence(provider_reliability=reliability),
        context=context(),
    )

    assert reliability.variable_metrics is before
    with pytest.raises(FrozenInstanceError):
        decision.reasons = ()
