from dataclasses import FrozenInstanceError, fields, replace

import pytest

from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonCategory as Category,
    RecommendationReasonScope as Scope,
)


def reason(basis=None, *, message=None, scope=Scope.TARGET, category=None):
    return RecommendationReason(
        scope=scope, category=category, basis=basis, message=message,
    )


def compare(primary=(), alternative=(), *, alternative_key="M42"):
    from decision.services.recommendation_comparison_builder import compare_recommendation_reasons

    return compare_recommendation_reasons(
        primary_catalog_key="M31",
        alternative_catalog_key=alternative_key,
        primary_reasons=primary,
        alternative_reasons=alternative,
    )


def test_comparison_has_exact_immutable_contract_and_snapshots_collections():
    from decision.models.recommendation_comparison import RecommendationComparison

    original = reason(message="Excellent rendement")
    source = [original]
    comparison = RecommendationComparison(
        primary_catalog_key="M31",
        alternative_catalog_key="M42",
        primary_only_reasons=source,
        alternative_only_reasons=[],
        shared_reasons=[],
    )
    assert [field.name for field in fields(comparison)] == [
        "primary_catalog_key", "alternative_catalog_key", "primary_only_reasons",
        "alternative_only_reasons", "shared_reasons",
    ]
    source.clear()
    assert comparison.primary_only_reasons == (original,)
    assert comparison.primary_only_reasons[0] is original
    assert comparison.alternative_only_reasons == comparison.shared_reasons == ()
    with pytest.raises(FrozenInstanceError):
        comparison.primary_catalog_key = "M33"
    with pytest.raises(TypeError):
        comparison.primary_only_reasons[0] = reason()


def test_same_machine_identity_is_shared_despite_different_other_fields():
    primary = replace(
        reason("selected_window_uncovered", category=Category.RELIABILITY),
        message="Primary wording", direction="positive", importance="primary",
        evidence_ref={"original": "primary"},
    )
    alternative = replace(
        primary, message="Alternative wording", direction="negative",
        importance="secondary", evidence_ref={"original": "alternative"},
    )
    primary_evidence = primary.evidence_ref
    alternative_evidence = alternative.evidence_ref
    comparison = compare((primary,), (alternative,))

    assert comparison.primary_catalog_key == "M31"
    assert comparison.alternative_catalog_key == "M42"
    assert comparison.primary_only_reasons == comparison.alternative_only_reasons == ()
    assert comparison.shared_reasons == (primary,)
    assert comparison.shared_reasons[0] is primary
    assert primary.message == "Primary wording"
    assert alternative.message == "Alternative wording"
    assert primary.evidence_ref is primary_evidence
    assert alternative.evidence_ref is alternative_evidence


def test_null_basis_never_matches_even_identical_text_or_the_same_object():
    original = reason(message="Excellent rendement")
    other = replace(original)
    comparison = compare((original, original), (original, other))

    assert comparison.shared_reasons == ()
    assert comparison.primary_only_reasons == (original, original)
    assert comparison.alternative_only_reasons == (original, other)
    assert comparison.alternative_only_reasons[1] is other


@pytest.mark.parametrize("changes", [
    {"scope": Scope.NIGHT},
    {"category": None},
    {"basis": "selected_window_coverage_unknown"},
])
def test_each_machine_identity_component_must_match_exactly(changes):
    primary = reason("selected_window_uncovered", category=Category.RELIABILITY)
    alternative = replace(primary, **changes)
    comparison = compare((primary,), (alternative,))

    assert comparison.shared_reasons == ()
    assert comparison.primary_only_reasons == (primary,)
    assert comparison.alternative_only_reasons == (alternative,)


def test_non_null_basis_is_not_tested_by_truthiness():
    primary = reason("")
    alternative = reason("", message="Different wording")
    comparison = compare((primary,), (alternative,))

    assert comparison.shared_reasons == (primary,)
    assert comparison.primary_only_reasons == comparison.alternative_only_reasons == ()


@pytest.mark.parametrize("primary_present, alternative_present", [
    (False, False), (True, False), (False, True), (True, True),
])
def test_empty_and_disjoint_collections_preserve_every_unmatched_reason(
    primary_present, alternative_present,
):
    primary = (reason(message="Excellent rendement"),) if primary_present else ()
    alternative = (reason(message="Projet prioritaire"),) if alternative_present else ()
    comparison = compare(primary, alternative)

    assert comparison.shared_reasons == ()
    assert comparison.primary_only_reasons == primary
    assert comparison.alternative_only_reasons == alternative


def test_original_order_and_object_identity_survive_partitioning():
    first_shared = reason("weather_not_fresh", scope=Scope.NIGHT)
    last_shared = reason("weather_snapshot_missing", scope=Scope.NIGHT)
    first_primary = reason(message="Excellent rendement")
    last_primary = reason("selected_window_uncovered")
    first_alternative = reason(message="Projet prioritaire")
    last_alternative = reason("provider_reliability_unavailable", scope=Scope.NIGHT)
    primary = [first_shared, first_primary, last_shared, last_primary]
    alternative = [first_alternative, replace(last_shared), last_alternative, replace(first_shared)]
    primary_before = tuple(primary)
    alternative_before = tuple(alternative)

    comparison = compare(primary, alternative)

    assert comparison.shared_reasons == (first_shared, last_shared)
    assert comparison.primary_only_reasons == (first_primary, last_primary)
    assert comparison.alternative_only_reasons == (first_alternative, last_alternative)
    assert comparison.shared_reasons[0] is first_shared
    assert comparison.shared_reasons[1] is last_shared
    assert tuple(primary) == primary_before
    assert tuple(alternative) == alternative_before


@pytest.mark.parametrize("primary_count, alternative_count", [(3, 1), (1, 3), (3, 3)])
def test_duplicate_identities_match_in_order_without_dropping_unmatched_occurrences(
    primary_count, alternative_count,
):
    primary = tuple(
        reason("weather_not_fresh", message=f"Primary {index}")
        for index in range(primary_count)
    )
    alternative = tuple(
        reason("weather_not_fresh", message=f"Alternative {index}")
        for index in range(alternative_count)
    )
    comparison = compare(primary, alternative)
    matched_count = min(primary_count, alternative_count)

    assert comparison.shared_reasons == primary[:matched_count]
    assert comparison.primary_only_reasons == primary[matched_count:]
    assert comparison.alternative_only_reasons == alternative[matched_count:]
    assert all(
        shared is original
        for shared, original in zip(comparison.shared_reasons, primary)
    )


def test_multiple_alternatives_are_compared_independently_against_same_primary():
    first = reason("weather_snapshot_missing", scope=Scope.NIGHT)
    second = reason("selected_window_uncovered")
    primary = (first, second)
    first_comparison = compare(primary, (replace(first),))
    second_comparison = compare(primary, (replace(second),), alternative_key="M33")
    repeated = compare(primary, (replace(first),))

    assert first_comparison.shared_reasons == (first,)
    assert first_comparison.primary_only_reasons == (second,)
    assert second_comparison.shared_reasons == (second,)
    assert second_comparison.primary_only_reasons == (first,)
    assert second_comparison.alternative_catalog_key == "M33"
    assert repeated == first_comparison
    assert primary == (first, second)


@pytest.mark.parametrize("primary, alternative", [
    (["Excellent rendement"], []), ([], ["weather_not_fresh"]),
])
def test_comparison_accepts_existing_structured_reasons_only(primary, alternative):
    with pytest.raises(TypeError):
        compare(primary, alternative)
