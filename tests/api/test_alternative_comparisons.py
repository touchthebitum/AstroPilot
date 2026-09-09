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
        assert payload["alternatives"][0]["reasons"] == []
        assert payload["alternatives"][1]["reasons"][0] == {
            "scope": "target",
            "category": None,
            "direction": None,
            "importance": None,
            "basis": None,
            "message": "Projet prioritaire",
            "rendered": None,
        }
        assert payload["alternatives"][1]["reasons"][1]["basis"] == (
            "provider_reliability_unavailable"
        )
        assert payload["alternatives"][1]["reasons"][1]["rendered"][
            "presentation_key"
        ] == "provider_reliability_unavailable"
        assert all("reasons" not in entry for entry in payload["shortlist_entries"])
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
        "rendered_reasons",
    }
    rendering = schemas[
        reason["properties"]["rendered_reasons"]["items"]["$ref"].split("/")[-1]
    ]
    assert set(rendering["properties"]) == {
        "presentation_key",
        "classic_text",
        "pro_text",
    }

    primary_field = public["properties"]["primary_reasons"]
    assert primary_field["type"] == "array"
    assert "primary_reasons" not in public.get("required", [])
    primary_reason = schemas[primary_field["items"]["$ref"].split("/")[-1]]
    assert set(primary_reason["properties"]) == {
        "scope", "category", "direction", "importance", "basis", "message", "rendered",
    }

    alternative_field = public["properties"]["alternatives"]
    alternative = schemas[alternative_field["items"]["$ref"].split("/")[-1]]
    assert set(alternative["properties"]) == {
        "target", "catalog_key", "provenance", "decision_score", "final_score",
        "target_decision_status", "reasons",
    }
    alternative_reason = schemas[
        alternative["properties"]["reasons"]["items"]["$ref"].split("/")[-1]
    ]
    assert set(alternative_reason["properties"]) == {
        "scope", "category", "direction", "importance", "basis", "message", "rendered",
    }
    shortlist_field = public["properties"]["shortlist_entries"]
    shortlist = schemas[shortlist_field["items"]["$ref"].split("/")[-1]]
    assert "reasons" not in shortlist["properties"]


def test_api_exposes_primary_reasons_without_requiring_alternatives(monkeypatch):
    primary = candidate("M31", ("Excellent rendement",))
    result = TonightResult(
        night=None,
        recommendation=Recommendation(
            opportunity=Opportunity(action=Action.START_PROJECT, candidate=primary),
            confidence=None,
        ),
        mission=NightMission(
            target="M31", confidence=None,
            window_start=START, window_end=START + timedelta(hours=2),
            recommended_hours=2.0,
        ),
    )
    monkeypatch.setattr(app_module, "_assess_shortlist_candidates", lambda *a, **kw: {})

    response = client_for(result).post("/v1/tonight", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["alternatives"] == payload["alternative_comparisons"] == []
    assert payload["primary_reasons"][0] == {
        "scope": "target",
        "category": None,
        "direction": None,
        "importance": None,
        "basis": None,
        "message": "Excellent rendement",
        "rendered": None,
    }
    assert payload["primary_reasons"][1]["basis"] == "provider_reliability_unavailable"
    assert payload["primary_reasons"][1]["rendered"] == {
        "presentation_key": "provider_reliability_unavailable",
        "classic_text": "La fiabilité historique du fournisseur météo n’est pas disponible.",
        "pro_text": (
            "Aucune évaluation historique de fiabilité du fournisseur météo "
            "n’est disponible pour ce contexte."
        ),
    }


def test_api_primary_reasons_default_empty_without_exposed_recommendation():
    result = TonightResult(None, None, None, status=TonightStatus.NO_RECOMMENDATION)
    payload = client_for(result).post("/v1/tonight", json={}).json()
    assert payload["primary_reasons"] == []


def test_api_preserves_stable_reason_codes_and_legacy_messages_exactly(monkeypatch):
    from decision.models.recommendation_reason import (
        RecommendationReason,
        RecommendationReasonCategory,
        RecommendationReasonScope,
    )

    stable_basis = "Provider.Mixed_CASE:cloud cover:évidence v1"
    primary = candidate("M31")
    alternative = candidate("M42")
    result = TonightResult(
        night=None,
        recommendation=Recommendation(
            opportunity=Opportunity(
                action=Action.START_PROJECT,
                candidate=primary,
                shortlist_entries=(alternative,),
            ),
            confidence=None,
        ),
        mission=NightMission(
            target="M31",
            confidence=None,
            window_start=START,
            window_end=START + timedelta(hours=2),
            recommended_hours=2.0,
        ),
    )
    reason_sets = {
        "M31": (
            RecommendationReason(
                category=RecommendationReasonCategory.RELIABILITY,
                scope=RecommendationReasonScope.NIGHT,
                direction="existing-direction",
                importance="existing-importance",
                basis=stable_basis,
                message="First existing message",
            ),
            RecommendationReason(
                scope=RecommendationReasonScope.TARGET,
                basis=None,
                message=stable_basis,
            ),
        ),
        "M42": (
            RecommendationReason(
                category=RecommendationReasonCategory.RELIABILITY,
                scope=RecommendationReasonScope.NIGHT,
                direction="other-existing-direction",
                importance="other-existing-importance",
                basis=stable_basis,
                message="Different existing message",
            ),
            RecommendationReason(
                scope=RecommendationReasonScope.TARGET,
                basis=None,
                message=stable_basis,
            ),
        ),
    }
    monkeypatch.setattr(
        Opportunity,
        "structured_reasons",
        property(lambda self: reason_sets[self.candidate.catalog_key]),
    )
    monkeypatch.setattr(
        app_module,
        "candidate_reasons",
        lambda source: reason_sets[source.catalog_key],
    )
    monkeypatch.setattr(
        app_module,
        "primary_window_reasons",
        lambda **kwargs: (),
    )
    monkeypatch.setattr(
        app_module,
        "candidate_assessment_reasons",
        lambda **kwargs: (),
    )
    monkeypatch.setattr(
        app_module,
        "_assess_shortlist_candidates",
        lambda *args, **kwargs: {
            "M42": assessment(WeatherTrustDecision(
                Quality.SUFFICIENT,
                Admissibility.ADMISSIBLE,
                (),
            ))
        },
    )

    response = client_for(result).post("/v1/tonight", json={})
    assert response.status_code == 200
    payload = response.json()
    comparison = payload["alternative_comparisons"][0]
    assert payload["alternatives"][0]["reasons"] == [
        {
            "scope": "night",
            "category": "reliability",
            "direction": "other-existing-direction",
            "importance": "other-existing-importance",
            "basis": stable_basis,
            "message": "Different existing message",
            "rendered": None,
        },
        {
            "scope": "target",
            "category": None,
            "direction": None,
            "importance": None,
            "basis": None,
            "message": stable_basis,
            "rendered": None,
        },
    ]
    assert comparison["shared_reasons"] == [{
        "category": "reliability",
        "scope": "night",
        "direction": "existing-direction",
        "importance": "existing-importance",
        "basis": stable_basis,
        "message": "First existing message",
        "evidence_ref": None,
        "rendered_reasons": [],
    }]
    assert comparison["primary_only_reasons"] == [{
        "category": None,
        "scope": "target",
        "direction": None,
        "importance": None,
        "basis": None,
        "message": stable_basis,
        "evidence_ref": None,
        "rendered_reasons": [],
    }]
    assert comparison["alternative_only_reasons"] == [{
        "category": None,
        "scope": "target",
        "direction": None,
        "importance": None,
        "basis": None,
        "message": stable_basis,
        "evidence_ref": None,
        "rendered_reasons": [],
    }]
