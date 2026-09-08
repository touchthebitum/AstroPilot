from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import decision.services.candidate_assessment as module
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.services.candidate_assessment import CandidateAssessment
from decision.validation.weather_window_coverage import WeatherWindowCoverageError
from decision.weather.provider_reliability import WeatherLocation
from decision.weather.weather_ingress import WeatherFreshness, WeatherSnapshot
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
)


START = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
END = START + timedelta(hours=9)
SITE = WeatherLocation(46.7508, 6.5495)


def snapshot():
    return WeatherSnapshot(
        payload={"hourly": "original snapshot"},
        provider="Open-Meteo",
        retrieved_at_utc=START - timedelta(minutes=5),
        requested_latitude=SITE.latitude,
        requested_longitude=SITE.longitude,
        grid_latitude=SITE.latitude,
        grid_longitude=SITE.longitude,
        grid_distance_km=0.0,
        elevation_m=837.0,
        timezone="Europe/Zurich",
        timezone_source="coordinates_local",
        utc_offset_seconds=7200,
        valid_from=START,
        valid_until=END,
        hour_count=24,
        completeness=1.0,
    )


def productive_window(start, end):
    return ProductiveWindowAssessment(
        window_start=start,
        window_end=end,
        recommended_hours=1.0,
        expected_gain=0.0,
        productivity=SimpleNamespace(windows=[object()]),
    )


def arrange(monkeypatch, assessment):
    captured = {}
    evaluation = {
        "catalog_key": "M31",
        "decision_context": object(),
        "selected_window_weather": object(),
    }
    profile = {"projects": {}}
    mission_input = object()

    def build_mission_input(value, *, profile):
        captured["evaluation"] = value
        captured["profile"] = profile
        return mission_input

    def build_productive_window(**kwargs):
        captured["productive_window_inputs"] = kwargs
        return assessment

    monkeypatch.setattr(
        module.ProductiveWindowAssessment,
        "build",
        build_productive_window,
    )
    result = CandidateAssessment.build(
        candidate=SimpleNamespace(catalog_key="M31"),
        object_evaluations={"M31": evaluation},
        profile=profile,
        weather_snapshot=snapshot(),
        weather_freshness=WeatherFreshness(5.0, "fresh", 90),
        decision_location=SITE,
        build_mission_input=build_mission_input,
    )
    return result, captured, evaluation, profile, mission_input


def test_candidate_assessment_is_immutable_and_uses_retained_evaluation(
    monkeypatch,
):
    assessment = productive_window(START + timedelta(hours=1), END)

    result, captured, evaluation, profile, mission_input = arrange(
        monkeypatch,
        assessment,
    )

    assert [field.name for field in fields(result)] == [
        "productive_window",
        "weather_decision",
    ]
    assert result.productive_window is assessment
    assert captured["evaluation"] is evaluation
    assert captured["profile"] is profile
    assert captured["productive_window_inputs"] == {
        "target": "M31",
        "context": evaluation["decision_context"],
        "mission_input": mission_input,
    }
    assert result.weather_decision.evidence_quality is (
        WeatherEvidenceQuality.INSUFFICIENT
    )
    assert result.weather_decision.admissibility is (
        WeatherDecisionAdmissibility.CAUTION
    )
    assert result.weather_decision.reasons == (
        "provider_reliability_unavailable",
    )
    with pytest.raises(FrozenInstanceError):
        result.weather_decision = None


def test_candidate_assessment_refuses_uncovered_candidate_window(monkeypatch):
    result, *_ = arrange(
        monkeypatch,
        productive_window(START - timedelta(hours=1), END),
    )

    assert result.weather_decision.evidence_quality is (
        WeatherEvidenceQuality.INSUFFICIENT
    )
    assert result.weather_decision.admissibility is (
        WeatherDecisionAdmissibility.REFUSED
    )
    assert result.weather_decision.reasons == ("selected_window_uncovered",)


def test_candidate_assessment_preserves_invalid_window_exception(monkeypatch):
    with pytest.raises(WeatherWindowCoverageError) as caught:
        arrange(
            monkeypatch,
            productive_window(START.replace(tzinfo=None), END),
        )

    assert caught.value.issues == ("invalid_mission_window",)
