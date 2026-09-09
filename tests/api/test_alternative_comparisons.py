from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import astropilot.app as app_module
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.mission.night_mission import NightMission
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.candidate_rejection import CandidateRejection, CandidateRejectionBasis
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.candidate_assessment import CandidateAssessment
from decision.services.tonight_application_service import TonightResult, TonightStatus
from decision.weather.weather_ingress import WeatherSnapshot
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility as Admissibility,
    WeatherEvidenceQuality as Quality,
    WeatherTrustDecision,
)


REFERENCE = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
START = REFERENCE + timedelta(hours=2)


def candidate(key, reasons=()):
    return Candidate(
        name=key, catalog_key=key, priority=0, astro_score=0, final_score=0,
        decision_score=10, portfolio_score=0, global_score=0, setup_score=0,
        best_setup=None, closure_bonus=0, reasons=list(reasons),
    )


def client_for(result, *, refused=False):
    weather = WeatherSnapshot(
        payload={"hourly": {}}, provider="Open-Meteo",
        retrieved_at_utc=REFERENCE - timedelta(minutes=5),
        requested_latitude=46.7508, requested_longitude=6.5495,
        grid_latitude=46.75, grid_longitude=6.55, grid_distance_km=0.1,
        elevation_m=837, timezone="Europe/Zurich", timezone_source="coordinates_local",
        utc_offset_seconds=7200, valid_from=REFERENCE - timedelta(hours=20),
        valid_until=START + timedelta(hours=1 if refused else 24),
        hour_count=48, completeness=1.0,
    )
    profile = {
        "location": {"name": "Buttes", "latitude": 46.7508, "longitude": 6.5495},
        "preferences": {"bortle": 3}, "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
    }
    return TestClient(app_module.create_app(
        service_factory=lambda: SimpleNamespace(evaluate=lambda **kwargs: result),
        weather_provider=lambda lat, lon: weather,
        profile_provider=lambda: profile, clock=lambda: REFERENCE,
    ))


def assessment(decision):
    return CandidateAssessment(
        productive_window=ProductiveWindowAssessment(
            window_start=START, window_end=START + timedelta(hours=2),
            recommended_hours=1.0, expected_gain=0.0,
            productivity=SimpleNamespace(
                astronomical_hours=2.0, productive_hours=1.0, confidence=0.5,
                windows=[SimpleNamespace(start_hour=0.0, end_hour=1.0,
                                         productivity=0.8, productive=True)],
            ),
        ),
        weather_decision=decision,
    )


@pytest.mark.parametrize("refused", [False, True])
def test_api_comparisons_match_only_exposed_alternatives_in_order(monkeypatch, refused):
    import decision.services.tonight_comparisons as comparisons

    primary = candidate("M31", ("Excellent rendement",))
    excluded = candidate("M33")
    empty = candidate("M42")
    second = candidate("M45", ("Projet prioritaire",))
    capped = candidate("M51")
    result = TonightResult(
        night=None,
        recommendation=Recommendation(
            opportunity=Opportunity(
                action=Action.START_PROJECT, candidate=primary,
                shortlist_entries=(excluded, empty, second, capped),
            ),
            confidence=None,
        ),
        mission=NightMission(
            target="M31", confidence=None,
            window_start=START, window_end=START + timedelta(hours=2),
            recommended_hours=2.0,
        ),
        candidate_rejections=(CandidateRejection(
            target="M81", catalog_key="M81", provenance=CandidateProvenance.DISCOVERY,
            basis=CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE, evaluation_score=0,
        ),),
    )
    admissible = WeatherTrustDecision(Quality.SUFFICIENT, Admissibility.ADMISSIBLE, ())
    caution = WeatherTrustDecision(Quality.INSUFFICIENT, Admissibility.CAUTION,
                                   ("provider_reliability_unavailable",))
    insufficiency = WeatherTrustDecision(Quality.INSUFFICIENT, Admissibility.REFUSED,
                                        ("selected_window_uncovered",))
    assessments = {
        "M33": assessment(insufficiency), "M42": assessment(admissible),
        "M45": assessment(caution), "M51": assessment(admissible),
    }
    monkeypatch.setattr(app_module, "_assess_shortlist_candidates", lambda *a, **kw: assessments)
    calls = []
    original = comparisons.compare_recommendation_reasons

    def record(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(comparisons, "compare_recommendation_reasons", record)
    response = client_for(result, refused=refused).post("/v1/tonight", json={})
    assert response.status_code == 200, response.json()
    payload = response.json()
    entries = payload["alternative_comparisons"]
    assert len(entries) == len(payload["alternatives"])
    expected = [] if refused else ["M42", "M45"]
    assert [entry["alternative_catalog_key"] for entry in entries] == expected
    assert [entry["catalog_key"] for entry in payload["alternatives"]] == expected
    assert [call["alternative_catalog_key"] for call in calls] == expected
    assert all(entry["primary_catalog_key"] == "M31" for entry in entries)
    if not refused:
        assert entries[0]["primary_only_reasons"][0]["message"] == "Excellent rendement"
        assert entries[0]["alternative_only_reasons"] == entries[0]["shared_reasons"] == []
        assert entries[1]["shared_reasons"][0]["basis"] == "provider_reliability_unavailable"
        assert entries[1]["alternative_only_reasons"][0]["message"] == "Projet prioritaire"
        assert payload["target_decision_status"] == "recommended"
        assert [entry["catalog_key"] for entry in payload["shortlist_entries"]] == [
            "M33", "M42", "M45", "M51",
        ]
    assert [entry["catalog_key"] for entry in payload["rejected_targets"]] == ["M81"]
    assert "M33" in [entry["catalog_key"] for entry in payload["insufficient_evidence_targets"]]
    assert result.recommendation.opportunity.candidate is primary


def test_api_comparisons_default_to_empty_and_have_exact_public_schema():
    result = TonightResult(None, None, None, status=TonightStatus.NO_RECOMMENDATION)
    client = client_for(result)
    response = client.post("/v1/tonight", json={})
    assert response.status_code == 200
    assert response.json()["alternative_comparisons"] == response.json()["alternatives"] == []
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    public = schemas["TonightResponseModel"]
    field = public["properties"]["alternative_comparisons"]
    assert field["type"] == "array"
    assert "alternative_comparisons" not in public.get("required", [])
    comparison = schemas[field["items"]["$ref"].split("/")[-1]]
    assert set(comparison["properties"]) == {
        "primary_catalog_key", "alternative_catalog_key", "primary_only_reasons",
        "alternative_only_reasons", "shared_reasons",
    }
    reason = schemas[comparison["properties"]["shared_reasons"]["items"]["$ref"].split("/")[-1]]
    assert set(reason["properties"]) == {
        "category", "scope", "direction", "importance", "basis", "message", "evidence_ref",
    }
