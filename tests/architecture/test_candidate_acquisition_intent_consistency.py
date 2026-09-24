import pytest

from decision.models.acquisition_intent_assessment import (
    AcquisitionIntentAssessment,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityStatus,
)
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelectionStatus,
)
from decision.models.candidate import Candidate


def assessment(intent_id, status):
    reason_codes = {
        AcquisitionIntentEligibilityStatus.ELIGIBLE: (),
        AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE: (
            "required_filter_unavailable",
        ),
        AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE: (
            "weather_evidence_insufficient",
        ),
    }[status]
    return AcquisitionIntentAssessment(
        acquisition_intent_id=intent_id,
        filter_type="Ha",
        label=f"Hα · {intent_id}",
        status=status,
        reason_codes=reason_codes,
    )


def candidate(*, status, selected, viable, assessments):
    return Candidate(
        name="Sh2-129/Ou4",
        catalog_key="Sh2-129",
        priority=1.0,
        astro_score=2.0,
        final_score=3.0,
        decision_score=4.0,
        portfolio_score=5.0,
        global_score=6.0,
        setup_score=7.0,
        best_setup="narrowband",
        closure_bonus=0.0,
        imaging_field_id="sh2-129_ou4",
        selected_acquisition_intent_id=selected,
        viable_acquisition_intent_ids=viable,
        acquisition_intent_selection_status=status,
        acquisition_intent_assessments=assessments,
    )


ELIGIBLE = AcquisitionIntentEligibilityStatus.ELIGIBLE
NOT_ELIGIBLE = AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE
INSUFFICIENT = AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    ("status", "selected", "viable", "assessments"),
    [
        (
            AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT,
            None,
            (),
            (assessment("A", ELIGIBLE),),
        ),
        (
            AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
            "A",
            ("A",),
            (assessment("A", NOT_ELIGIBLE), assessment("B", ELIGIBLE)),
        ),
        (
            AcquisitionIntentSelectionStatus.PREFERRED,
            "A",
            ("A",),
            (assessment("A", NOT_ELIGIBLE), assessment("B", ELIGIBLE)),
        ),
        (
            AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE,
            None,
            ("A", "B"),
            (assessment("A", ELIGIBLE), assessment("B", NOT_ELIGIBLE)),
        ),
    ],
)
def test_candidate_rejects_selection_contradicting_non_empty_assessments(
    status,
    selected,
    viable,
    assessments,
):
    with pytest.raises(ValueError):
        candidate(
            status=status,
            selected=selected,
            viable=viable,
            assessments=assessments,
        )


@pytest.mark.parametrize(
    ("status", "selected", "viable", "assessments"),
    [
        (
            AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT,
            None,
            (),
            (assessment("A", NOT_ELIGIBLE),),
        ),
        (
            AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
            "A",
            ("A",),
            (assessment("A", ELIGIBLE), assessment("B", NOT_ELIGIBLE)),
        ),
        (
            AcquisitionIntentSelectionStatus.PREFERRED,
            "A",
            ("A",),
            (assessment("A", ELIGIBLE), assessment("B", ELIGIBLE)),
        ),
        (
            AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE,
            None,
            ("A", "B"),
            (
                assessment("A", ELIGIBLE),
                assessment("B", ELIGIBLE),
                assessment("C", NOT_ELIGIBLE),
            ),
        ),
    ],
)
def test_candidate_accepts_each_coherent_selection_projection(
    status,
    selected,
    viable,
    assessments,
):
    value = candidate(
        status=status,
        selected=selected,
        viable=viable,
        assessments=assessments,
    )

    assert value.acquisition_intent_assessments is assessments


def test_non_viable_refused_and_insufficient_assessments_do_not_conflict():
    assessments = (
        assessment("A", ELIGIBLE),
        assessment("B", NOT_ELIGIBLE),
        assessment("C", INSUFFICIENT),
    )

    value = candidate(
        status=AcquisitionIntentSelectionStatus.PREFERRED,
        selected="A",
        viable=("A",),
        assessments=assessments,
    )

    assert value.acquisition_intent_assessments == assessments


def test_legacy_empty_assessments_keep_existing_selection_contract_only():
    value = candidate(
        status=AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
        selected="A",
        viable=("A",),
        assessments=(),
    )

    assert value.acquisition_intent_assessments == ()
