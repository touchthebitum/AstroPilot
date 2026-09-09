from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonCategory as Category,
    RecommendationReasonScope as Scope,
)
from decision.services.recommendation_comparison_builder import compare_recommendation_reasons
from decision.services.tonight_application_service import TonightResult, TonightStatus
from decision.services.tonight_response import TonightResponse
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


def test_comparison_response_is_immutable_and_preserves_existing_structured_fields():
    from decision.services.tonight_comparisons import comparison_response

    evidence = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT,
        WeatherDecisionAdmissibility.CAUTION,
        ("provider_reliability_unavailable",),
    )
    shared = RecommendationReason(
        category=Category.RELIABILITY, scope=Scope.NIGHT,
        basis=evidence.reasons[0], evidence_ref=evidence,
    )
    primary_text = RecommendationReason(scope=Scope.TARGET, message="Excellent rendement")
    alternative_text = RecommendationReason(scope=Scope.TARGET, message="Projet prioritaire")
    original = compare_recommendation_reasons(
        primary_catalog_key="M31", alternative_catalog_key="M42",
        primary_reasons=(primary_text, shared), alternative_reasons=(shared, alternative_text),
    )
    response = comparison_response(original)
    assert [f.name for f in fields(response)] == [
        "primary_catalog_key", "alternative_catalog_key", "primary_only_reasons",
        "alternative_only_reasons", "shared_reasons",
    ]
    assert response.primary_catalog_key == original.primary_catalog_key
    assert response.alternative_catalog_key == original.alternative_catalog_key
    for source_reasons, response_reasons in (
        (original.primary_only_reasons, response.primary_only_reasons),
        (original.alternative_only_reasons, response.alternative_only_reasons),
        (original.shared_reasons, response.shared_reasons),
    ):
        assert isinstance(response_reasons, tuple)
        assert len(source_reasons) == len(response_reasons)
        for source, mapped in zip(source_reasons, response_reasons):
            assert [f.name for f in fields(mapped)] == [
                "category", "scope", "direction", "importance", "basis", "message", "evidence_ref",
            ]
            for f in fields(source):
                assert getattr(mapped, f.name) is getattr(source, f.name)
    with pytest.raises(FrozenInstanceError):
        response.alternative_catalog_key = "M33"
    with pytest.raises(FrozenInstanceError):
        response.shared_reasons[0].message = "changed"
    with pytest.raises(TypeError):
        response.shared_reasons[0] = response.shared_reasons[0]


def test_comparison_response_builder_delegates_once_per_alternative_in_order(monkeypatch):
    import decision.services.tonight_comparisons as module

    primary = (RecommendationReason(scope=Scope.TARGET, message="Excellent rendement"),)
    second = (RecommendationReason(scope=Scope.TARGET, message="Projet prioritaire"),)
    alternatives = (("Z", ()), ("A", second))
    calls = []

    def record(**kwargs):
        calls.append(kwargs)
        return compare_recommendation_reasons(**kwargs)

    monkeypatch.setattr(module, "compare_recommendation_reasons", record)
    responses = module.build_alternative_comparisons(
        primary_catalog_key="M31", primary_reasons=primary, alternatives=alternatives,
    )
    assert [response.alternative_catalog_key for response in responses] == ["Z", "A"]
    assert calls == [
        dict(primary_catalog_key="M31", alternative_catalog_key=key,
             primary_reasons=primary, alternative_reasons=reasons)
        for key, reasons in alternatives
    ]
    assert [reason.message for reason in responses[0].primary_only_reasons] == ["Excellent rendement"]
    assert responses[0].alternative_only_reasons == responses[0].shared_reasons == ()
    assert module.build_alternative_comparisons(
        primary_catalog_key="M31", primary_reasons=primary, alternatives=(),
    ) == ()
    assert len(calls) == 2


def test_tonight_only_serializes_already_built_comparisons(monkeypatch):
    import decision.services.tonight_comparisons as module

    entry, = module.build_alternative_comparisons(
        primary_catalog_key="M31", primary_reasons=(), alternatives=(("M42", ()),),
    )

    def forbidden(**kwargs):
        raise AssertionError("Serialization must not build comparisons")

    monkeypatch.setattr(module, "compare_recommendation_reasons", forbidden)
    result = TonightResult(None, None, None, status=TonightStatus.NO_RECOMMENDATION)
    baseline = TonightResponse.from_result(result).to_dict()
    assert baseline.pop("alternative_comparisons") == []
    response = TonightResponse.from_result(result, alternative_comparisons=(entry,)).to_dict()
    assert response.pop("alternative_comparisons") == [{
        "primary_catalog_key": "M31", "alternative_catalog_key": "M42",
        "primary_only_reasons": [], "alternative_only_reasons": [], "shared_reasons": [],
    }]
    assert response == baseline


def test_structured_evidence_is_serialized_without_inventing_an_identifier():
    from decision.services.tonight_comparisons import build_alternative_comparisons

    evidence = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT, WeatherDecisionAdmissibility.CAUTION,
        ("provider_reliability_unavailable",),
    )
    reasons = evidence.structured_reasons
    entries = build_alternative_comparisons(
        primary_catalog_key="M31", primary_reasons=reasons, alternatives=(("M42", reasons),),
    )
    payload = TonightResponse(status="available", alternative_comparisons=list(entries)).to_dict()
    assert payload["alternative_comparisons"][0]["shared_reasons"] == [{
        "category": "reliability", "scope": "night", "direction": None,
        "importance": None, "basis": "provider_reliability_unavailable", "message": None,
        "evidence_ref": {
            "evidence_quality": "insufficient", "admissibility": "caution",
            "reasons": ["provider_reliability_unavailable"],
        },
    }]
