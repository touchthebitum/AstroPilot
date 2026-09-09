from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonCategory,
    RecommendationReasonScope,
)


VERIFIED_PRESENTATION_BASES = (
    "selected_window_uncovered",
    "selected_window_coverage_unknown",
    "weather_provider_mismatch",
    "weather_location_mismatch",
    "weather_snapshot_missing",
    "weather_freshness_missing",
    "weather_not_fresh",
    "provider_reliability_context_missing",
    "provider_reliability_unavailable",
    "provider_report_scope_mismatch",
    "provider_context_not_evaluated",
)


def reason(*, basis, message=None):
    return RecommendationReason(
        category=RecommendationReasonCategory.RELIABILITY,
        scope=RecommendationReasonScope.NIGHT,
        basis=basis,
        message=message,
    )


def test_presentation_contract_is_immutable_and_contains_exactly_two_fields():
    from decision.models.recommendation_reason_presentation import (
        RecommendationReasonPresentation,
    )

    presentation = RecommendationReasonPresentation(
        basis="weather_not_fresh",
        presentation_key="weather_not_fresh",
    )

    assert [field.name for field in fields(presentation)] == [
        "basis",
        "presentation_key",
    ]
    with pytest.raises(FrozenInstanceError):
        presentation.presentation_key = "changed"


@pytest.mark.parametrize("basis", VERIFIED_PRESENTATION_BASES)
def test_verified_basis_maps_explicitly_without_renaming_or_mode_variants(basis):
    from decision.services.recommendation_reason_presentation import (
        recommendation_reason_presentation,
    )

    source = reason(basis=basis)
    first = recommendation_reason_presentation(source)
    second = recommendation_reason_presentation(source)

    assert first is not None
    assert first.basis == basis
    assert first.presentation_key == basis
    assert second == first
    assert source.basis == basis


def test_legacy_reason_never_maps_from_message_text():
    from decision.services.recommendation_reason_presentation import (
        recommendation_reason_presentation,
    )

    for message in VERIFIED_PRESENTATION_BASES:
        source = RecommendationReason(
            scope=RecommendationReasonScope.TARGET,
            basis=None,
            message=message,
        )
        assert recommendation_reason_presentation(source) is None
        assert source.basis is None
        assert source.message == message


@pytest.mark.parametrize(
    "basis",
    [
        "unverified_code",
        "provider_evidence_missing:cloud_cover_percent",
        "provider_evidence_insufficient:cloud_cover_percent",
        "maximum_absolute_error:cloud_cover_percent:5",
        "provider_context_excluded:unverified_detail",
        "provider_comparison_excluded:unverified_detail",
        "Weather_Not_Fresh",
        " weather_not_fresh ",
        "",
    ],
)
def test_unverified_or_reconstructed_basis_does_not_receive_a_mapping(basis):
    from decision.services.recommendation_reason_presentation import (
        recommendation_reason_presentation,
    )

    source = reason(basis=basis, message="Existing message")
    assert recommendation_reason_presentation(source) is None
    assert source.basis == basis
    assert source.message == "Existing message"


def test_presentation_mapping_accepts_structured_reasons_only():
    from decision.services.recommendation_reason_presentation import (
        recommendation_reason_presentation,
    )

    with pytest.raises(TypeError):
        recommendation_reason_presentation("weather_not_fresh")
