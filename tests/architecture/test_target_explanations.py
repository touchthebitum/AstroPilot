from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonCategory,
    RecommendationReasonScope,
)
from decision.services.tonight_alternative_reasons import alternative_reason_responses
from decision.services.tonight_primary_reasons import primary_reason_responses
from decision.services.tonight_response import TargetDecisionStatus


def test_target_explanations_preserve_bound_reason_objects_and_target_order():
    from decision.services.target_explanation import build_target_explanations

    primary_reasons = primary_reason_responses((
        RecommendationReason(
            scope=RecommendationReasonScope.TARGET,
            message="Excellent rendement",
        ),
        RecommendationReason(
            category=RecommendationReasonCategory.RELIABILITY,
            scope=RecommendationReasonScope.NIGHT,
            basis="weather_not_fresh",
        ),
    ))
    alternative_reasons = alternative_reason_responses((
        RecommendationReason(
            scope=RecommendationReasonScope.TARGET,
            message="Projet prioritaire",
        ),
    ))

    explanations = build_target_explanations(
        primary=("M31", primary_reasons),
        alternatives=(("M42", alternative_reasons), ("M45", ())),
    )

    assert [field.name for field in fields(explanations[0])] == [
        "catalog_key", "target_decision_status", "reasons",
    ]
    assert [entry.catalog_key for entry in explanations] == ["M31", "M42", "M45"]
    assert [entry.target_decision_status for entry in explanations] == [
        TargetDecisionStatus.RECOMMENDED,
        TargetDecisionStatus.VIABLE,
        TargetDecisionStatus.VIABLE,
    ]
    assert explanations[0].reasons == primary_reasons
    assert explanations[1].reasons == alternative_reasons
    assert explanations[2].reasons == ()
    assert explanations[0].reasons[0] is primary_reasons[0]
    assert explanations[1].reasons[0] is alternative_reasons[0]
    assert explanations[0].reasons[1].rendered is primary_reasons[1].rendered
    with pytest.raises(FrozenInstanceError):
        explanations[0].catalog_key = "M33"
    with pytest.raises(TypeError):
        explanations[0].reasons[0] = explanations[0].reasons[0]


def test_target_explanations_require_an_existing_bound_primary_collection():
    from decision.services.target_explanation import build_target_explanations

    assert build_target_explanations(primary=None, alternatives=()) == ()
    explanation, = build_target_explanations(
        primary=("M31", ()),
        alternatives=(),
    )
    assert explanation.catalog_key == "M31"
    assert explanation.target_decision_status is TargetDecisionStatus.RECOMMENDED
    assert explanation.reasons == ()


def test_target_explanation_responses_are_exact_immutable_and_preserve_order():
    from decision.services.target_explanation import (
        build_target_explanations,
        target_explanation_responses,
    )

    primary_reasons = primary_reason_responses((
        RecommendationReason(
            category=RecommendationReasonCategory.RELIABILITY,
            scope=RecommendationReasonScope.NIGHT,
            basis="weather_not_fresh",
        ),
    ))
    alternative_reasons = alternative_reason_responses((
        RecommendationReason(
            scope=RecommendationReasonScope.TARGET,
            message="Projet prioritaire",
        ),
    ))
    explanations = build_target_explanations(
        primary=("M31", primary_reasons),
        alternatives=(("M42", alternative_reasons), ("M45", ())),
    )

    responses = target_explanation_responses(explanations)

    assert [field.name for field in fields(responses[0])] == [
        "catalog_key", "target_decision_status", "reasons",
    ]
    assert [entry.catalog_key for entry in responses] == ["M31", "M42", "M45"]
    assert responses[0].reasons[0] is primary_reasons[0]
    assert responses[1].reasons[0] is alternative_reasons[0]
    assert responses[2].reasons == ()
    assert responses[0].reasons[0].rendered is primary_reasons[0].rendered
    with pytest.raises(FrozenInstanceError):
        responses[0].target_decision_status = TargetDecisionStatus.VIABLE
