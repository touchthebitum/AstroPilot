from dataclasses import fields

import pytest

from decision.engines.project_selection_engine import ProjectSelectionEngine
from decision.mission.mission_input import MissionInput
from decision.mission.night_mission import NightMission
from decision.models.acquisition_intent_selection import (
    MULTIPLE_NON_DOMINATED_INTENTS,
    NO_ELIGIBLE_INTENT,
    ONLY_ELIGIBLE_INTENT,
    UNIQUE_NON_DOMINATED_INTENT,
    AcquisitionIntentSelection,
    AcquisitionIntentSelectionStatus,
)
from decision.models.candidate import Candidate
from decision.models.context.session_context import SessionContext
from decision.models.session_availability import SessionAvailability
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation_engine import RecommendationEngine


def selection(
    status: AcquisitionIntentSelectionStatus,
) -> AcquisitionIntentSelection:
    values = {
        AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT: (
            None,
            (),
            NO_ELIGIBLE_INTENT,
        ),
        AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT: (
            " Ha_primary ",
            (" Ha_primary ",),
            ONLY_ELIGIBLE_INTENT,
        ),
        AcquisitionIntentSelectionStatus.PREFERRED: (
            "OIII.secondary",
            ("OIII.secondary",),
            UNIQUE_NON_DOMINATED_INTENT,
        ),
        AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE: (
            None,
            ("z-intent", "A_intent", "middle.intent"),
            MULTIPLE_NON_DOMINATED_INTENTS,
        ),
    }
    selected_id, viable_ids, reason_code = values[status]
    return AcquisitionIntentSelection(
        selected_acquisition_intent_id=selected_id,
        viable_acquisition_intent_ids=viable_ids,
        status=status,
        reason_codes=(reason_code,),
    )


def candidate_from(
    result: AcquisitionIntentSelection | None,
    *,
    decision_score: float = 10.0,
):
    return ProjectSelectionEngine.build_candidate(
        name="Flying Bat and Squid",
        catalog_key="Sh2-129",
        priority=1.0,
        astro_score=80.0,
        final_score=70.0,
        decision_score=decision_score,
        portfolio_score=10.0,
        global_score=80.0,
        setup_score=8.0,
        best_setup="widefield",
        closure_bonus=0.0,
        reasons=[],
        strategy_scores={},
        acquired_hours=2.0,
        imaging_field_id="sh2-129_ou4",
        acquisition_intent_selection=result,
    )


def test_candidate_exposes_additive_selection_contract_with_legacy_defaults():
    value = candidate_from(None)

    assert {
        field.name for field in fields(value)
    } >= {
        "selected_acquisition_intent_id",
        "viable_acquisition_intent_ids",
        "acquisition_intent_selection_status",
    }
    assert value.selected_acquisition_intent_id is None
    assert value.viable_acquisition_intent_ids == ()
    assert value.acquisition_intent_selection_status is None


@pytest.mark.parametrize("status", tuple(AcquisitionIntentSelectionStatus))
def test_candidate_copies_authoritative_selection_result_exactly(status):
    result = selection(status)

    value = candidate_from(result)

    assert (
        value.selected_acquisition_intent_id
        == result.selected_acquisition_intent_id
    )
    assert (
        value.viable_acquisition_intent_ids
        is result.viable_acquisition_intent_ids
    )
    assert value.acquisition_intent_selection_status is result.status


def test_no_clear_preference_preserves_order_and_selects_no_fallback():
    result = selection(AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE)

    candidate = candidate_from(result)
    opportunity = OpportunityEngine().evaluate(candidates=[candidate])
    recommendation = RecommendationEngine().recommend(opportunity=opportunity)

    assert recommendation is not None
    assert recommendation.opportunity.candidate is candidate
    assert candidate.selected_acquisition_intent_id is None
    assert candidate.viable_acquisition_intent_ids == (
        "z-intent",
        "A_intent",
        "middle.intent",
    )
    assert candidate.acquisition_intent_selection_status is (
        AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE
    )


def test_selection_provenance_does_not_change_existing_candidate_ranking():
    lower = candidate_from(
        selection(AcquisitionIntentSelectionStatus.PREFERRED),
        decision_score=1.0,
    )
    higher = candidate_from(
        selection(AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT),
        decision_score=2.0,
    )

    opportunity = OpportunityEngine().evaluate(candidates=[lower, higher])

    assert opportunity.candidate is higher


def test_builder_rejects_non_authoritative_selection_shape():
    with pytest.raises(TypeError, match="AcquisitionIntentSelection or None"):
        candidate_from({"selected_acquisition_intent_id": "invented"})


def test_candidate_rejects_partial_or_inconsistent_selection_provenance():
    legacy = candidate_from(None)
    values = {
        field.name: getattr(legacy, field.name)
        for field in fields(legacy)
    }
    values["viable_acquisition_intent_ids"] = ("invented",)

    with pytest.raises(ValueError, match="requires a selection status"):
        Candidate(**values)


def test_acquisition_intent_selection_does_not_expand_mission_or_session_models():
    for model in (MissionInput, NightMission, SessionContext, SessionAvailability):
        assert "selected_acquisition_intent_id" not in {
            field.name for field in fields(model)
        }
