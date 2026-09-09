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
                "category", "scope", "direction", "importance", "basis", "message",
                "evidence_ref", "rendered_reasons",
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
        "rendered_reasons": [{
            "presentation_key": "provider_reliability_unavailable",
            "classic_text": (
                "La fiabilité historique du fournisseur météo n’est pas disponible."
            ),
            "pro_text": (
                "Aucune évaluation historique de fiabilité du fournisseur météo "
                "n’est disponible pour ce contexte."
            ),
        }],
    }]


def test_reason_transport_preserves_stable_basis_and_legacy_none_exactly():
    from decision.models.recommendation_comparison import RecommendationComparison
    from decision.services.tonight_comparisons import comparison_response

    stable_basis = "Provider.Mixed_CASE:cloud cover:évidence v1"
    first = RecommendationReason(
        category=Category.RELIABILITY,
        scope=Scope.NIGHT,
        direction="existing-direction",
        importance="existing-importance",
        basis=stable_basis,
        message="First existing message",
    )
    second = RecommendationReason(
        category=Category.RELIABILITY,
        scope=Scope.NIGHT,
        direction="other-existing-direction",
        importance="other-existing-importance",
        basis=stable_basis,
        message="Different existing message",
    )
    legacy = RecommendationReason(
        scope=Scope.TARGET,
        basis=None,
        message=stable_basis,
    )
    response = comparison_response(RecommendationComparison(
        primary_catalog_key="M31",
        alternative_catalog_key="M42",
        primary_only_reasons=(legacy,),
        alternative_only_reasons=(),
        shared_reasons=(first, second),
    ))

    assert [reason.message for reason in response.shared_reasons] == [
        "First existing message",
        "Different existing message",
    ]
    assert [reason.basis for reason in response.shared_reasons] == [
        stable_basis,
        stable_basis,
    ]
    assert [reason.direction for reason in response.shared_reasons] == [
        "existing-direction",
        "other-existing-direction",
    ]
    assert [reason.importance for reason in response.shared_reasons] == [
        "existing-importance",
        "other-existing-importance",
    ]
    assert response.primary_only_reasons[0].basis is None
    assert response.primary_only_reasons[0].message == stable_basis


def test_rendered_reason_response_is_exact_immutable_and_bound_to_source_reason():
    from decision.models.recommendation_comparison import RecommendationComparison
    from decision.services.tonight_comparisons import comparison_response
    from decision.services.tonight_response import (
        RecommendationReasonRenderingResponse,
    )

    rendered = RecommendationReasonRenderingResponse(
        presentation_key="weather_not_fresh",
        classic_text="Les données météo ne sont pas assez récentes.",
        pro_text=(
            "La fraîcheur des données météo ne respecte pas le seuil requis pour "
            "la décision."
        ),
    )
    assert [field.name for field in fields(rendered)] == [
        "presentation_key",
        "classic_text",
        "pro_text",
    ]
    with pytest.raises(FrozenInstanceError):
        rendered.classic_text = "changed"

    renderable = RecommendationReason(
        category=Category.RELIABILITY,
        scope=Scope.NIGHT,
        basis="weather_not_fresh",
        message="Existing message remains unchanged",
    )
    legacy = RecommendationReason(
        scope=Scope.TARGET,
        basis=None,
        message="weather_not_fresh",
    )
    unsupported = RecommendationReason(
        category=Category.RELIABILITY,
        scope=Scope.NIGHT,
        basis="weather_provider_mismatch",
        message="Existing unsupported message",
    )
    response = comparison_response(RecommendationComparison(
        primary_catalog_key="M31",
        alternative_catalog_key="M42",
        primary_only_reasons=(renderable, legacy, unsupported),
        alternative_only_reasons=(),
        shared_reasons=(),
    ))

    assert [reason.basis for reason in response.primary_only_reasons] == [
        "weather_not_fresh",
        None,
        "weather_provider_mismatch",
    ]
    assert [reason.message for reason in response.primary_only_reasons] == [
        "Existing message remains unchanged",
        "weather_not_fresh",
        "Existing unsupported message",
    ]
    assert response.primary_only_reasons[0].rendered_reasons == (rendered,)
    assert response.primary_only_reasons[1].rendered_reasons == ()
    assert response.primary_only_reasons[2].rendered_reasons == ()


def test_rendered_reasons_preserve_structured_reason_order_and_duplicates():
    from decision.models.recommendation_comparison import RecommendationComparison
    from decision.services.tonight_comparisons import comparison_response

    reasons = (
        RecommendationReason(
            category=Category.RELIABILITY,
            scope=Scope.NIGHT,
            basis="provider_reliability_unavailable",
            message="First existing message",
        ),
        RecommendationReason(
            category=Category.RELIABILITY,
            scope=Scope.NIGHT,
            basis="weather_not_fresh",
            message="Second existing message",
        ),
        RecommendationReason(
            category=Category.RELIABILITY,
            scope=Scope.NIGHT,
            basis="provider_reliability_unavailable",
            message="Different existing message",
        ),
    )
    response = comparison_response(RecommendationComparison(
        primary_catalog_key="M31",
        alternative_catalog_key="M42",
        primary_only_reasons=reasons,
        alternative_only_reasons=(),
        shared_reasons=(),
    ))

    assert [reason.message for reason in response.primary_only_reasons] == [
        reason.message for reason in reasons
    ]
    assert [
        reason.rendered_reasons[0].presentation_key
        for reason in response.primary_only_reasons
    ] == [
        "provider_reliability_unavailable",
        "weather_not_fresh",
        "provider_reliability_unavailable",
    ]
