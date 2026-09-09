from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.recommendation.recommendation import Recommendation
from decision.services.target_explanation import TargetExplanation
from decision.services.tonight_response import TargetDecisionStatus
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
    UserSelectionValidationError,
    validate_user_selection,
)


SELECTED_AT = datetime(2026, 9, 9, 20, tzinfo=timezone.utc)


def context(*, decision_id="decision-1"):
    return UserSelectionDecisionContext(
        decision_id=decision_id,
        primary_catalog_key="M31",
        exposed_alternative_catalog_keys=("M42",),
        explicitly_evaluated_catalog_keys=("M31", "M42", "NGC7000"),
    )


def selection(source, selected_catalog_key, *, decision_id="decision-1"):
    return UserSelection(
        selection_id="selection-1",
        decision_id=decision_id,
        selected_catalog_key=selected_catalog_key,
        source=source,
        selected_at=SELECTED_AT,
    )


@pytest.mark.parametrize(
    ("source", "catalog_key"),
    [
        (UserSelectionSource.PRIMARY_RECOMMENDATION, "M31"),
        (UserSelectionSource.ALTERNATIVE, "M42"),
        (UserSelectionSource.OTHER_EVALUATED_TARGET, "NGC7000"),
        (UserSelectionSource.DECLINED, None),
    ],
)
def test_valid_user_selections_are_returned_unchanged(source, catalog_key):
    proposed = selection(source, catalog_key)

    validated = validate_user_selection(proposed, context())

    assert validated is proposed


def test_alternative_must_be_exposed_for_same_decision():
    proposed = selection(UserSelectionSource.ALTERNATIVE, "NGC7000")

    with pytest.raises(
        UserSelectionValidationError,
        match="selected_target_not_exposed_alternative",
    ):
        validate_user_selection(proposed, context())


def test_other_target_must_be_explicitly_evaluated_for_decision():
    proposed = selection(UserSelectionSource.OTHER_EVALUATED_TARGET, "M101")

    with pytest.raises(
        UserSelectionValidationError,
        match="selected_target_not_explicitly_evaluated",
    ):
        validate_user_selection(proposed, context())


def test_declined_selection_rejects_catalog_key():
    with pytest.raises(ValueError, match="declined_selection_requires_no_target"):
        selection(UserSelectionSource.DECLINED, "M31")


def test_non_declined_selection_requires_catalog_key():
    with pytest.raises(ValueError, match="selected_catalog_key_required"):
        selection(UserSelectionSource.ALTERNATIVE, None)


def test_selection_rejects_mismatched_decision_context():
    proposed = selection(
        UserSelectionSource.PRIMARY_RECOMMENDATION,
        "M31",
        decision_id="decision-2",
    )

    with pytest.raises(
        UserSelectionValidationError,
        match="user_selection_decision_mismatch",
    ):
        validate_user_selection(proposed, context(decision_id="decision-1"))


def test_alternative_selection_does_not_mutate_recommendation_or_primary_status():
    candidate = SimpleNamespace(catalog_key="M31")
    opportunity = SimpleNamespace(candidate=candidate)
    recommendation = Recommendation(opportunity=opportunity, confidence=0.9)
    primary_explanation = TargetExplanation(
        catalog_key="M31",
        target_decision_status=TargetDecisionStatus.RECOMMENDED,
        reasons=(),
    )

    validate_user_selection(
        selection(UserSelectionSource.ALTERNATIVE, "M42"),
        context(),
    )

    assert recommendation.opportunity is opportunity
    assert recommendation.opportunity.candidate is candidate
    assert primary_explanation.target_decision_status is TargetDecisionStatus.RECOMMENDED


def test_user_selection_is_immutable():
    proposed = selection(UserSelectionSource.PRIMARY_RECOMMENDATION, "M31")

    with pytest.raises(FrozenInstanceError):
        proposed.selected_catalog_key = "M42"


def test_context_copies_source_collections_without_mutating_them():
    alternatives = ["M42"]
    evaluated = ["M31", "M42", "NGC7000"]

    decision_context = UserSelectionDecisionContext(
        decision_id="decision-1",
        primary_catalog_key="M31",
        exposed_alternative_catalog_keys=alternatives,
        explicitly_evaluated_catalog_keys=evaluated,
    )
    alternatives.append("M101")
    evaluated.clear()

    assert decision_context.exposed_alternative_catalog_keys == ("M42",)
    assert decision_context.explicitly_evaluated_catalog_keys == (
        "M31",
        "M42",
        "NGC7000",
    )
