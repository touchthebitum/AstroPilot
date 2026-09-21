"""Pure V1 eligibility evaluator for a resolved acquisition intent."""

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment,
    AcquisitionIntentEligibilityReason,
    AcquisitionIntentEligibilityStatus,
    AcquisitionIntentEvidenceGap,
)
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.models.imaging_field import (
    AcquisitionIntent,
    ImagingFieldDefinition,
)
from decision.models.project_acquisition_intent_target import (
    ProjectAcquisitionIntentTarget,
)
from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress
from decision.models.session_availability import SessionAvailability
from decision.services.session_availability_windowing import (
    select_continuous_actionable_productive_window,
)
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


def _not_eligible(
    acquisition_intent_id: str,
    reason: AcquisitionIntentEligibilityReason,
) -> AcquisitionIntentEligibilityAssessment:
    return AcquisitionIntentEligibilityAssessment(
        acquisition_intent_id=acquisition_intent_id,
        status=AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE,
        blocking_reasons=(reason,),
        evidence_gaps=(),
    )


def evaluate_acquisition_intent_eligibility(
    *,
    acquisition_intent: AcquisitionIntent,
    imaging_field: ImagingFieldDefinition,
    project_targets: tuple[ProjectAcquisitionIntentTarget, ...],
    remaining_progress: AcquisitionIntentRemainingProgress | None = None,
    setup_filter_capabilities: SetupFilterCapabilities | None,
    productive_window: ProductiveWindowAssessment | None,
    session_availability: SessionAvailability | None,
    weather_trust_decision: WeatherTrustDecision | None,
) -> AcquisitionIntentEligibilityAssessment:
    """Evaluate resolved V1 gates without ranking or recommending an intent."""

    if not isinstance(acquisition_intent, AcquisitionIntent):
        raise TypeError("Expected AcquisitionIntent")
    if not isinstance(imaging_field, ImagingFieldDefinition):
        raise TypeError("Expected ImagingFieldDefinition")
    if not isinstance(project_targets, tuple) or not all(
        isinstance(target, ProjectAcquisitionIntentTarget)
        for target in project_targets
    ):
        raise TypeError(
            "project_targets_must_contain_project_acquisition_intent_targets"
        )
    if len({target.acquisition_intent_id for target in project_targets}) != len(
        project_targets
    ):
        raise ValueError("duplicate_project_acquisition_intent_target")
    if setup_filter_capabilities is not None and not isinstance(
        setup_filter_capabilities,
        SetupFilterCapabilities,
    ):
        raise TypeError("Expected SetupFilterCapabilities or None")
    if productive_window is not None and not isinstance(
        productive_window,
        ProductiveWindowAssessment,
    ):
        raise TypeError("Expected ProductiveWindowAssessment or None")
    if session_availability is not None and not isinstance(
        session_availability,
        SessionAvailability,
    ):
        raise TypeError("Expected SessionAvailability or None")
    if weather_trust_decision is not None and not isinstance(
        weather_trust_decision,
        WeatherTrustDecision,
    ):
        raise TypeError("Expected WeatherTrustDecision or None")

    intent_id = acquisition_intent.acquisition_intent_id
    matching_field_intents = tuple(
        intent
        for intent in imaging_field.acquisition_intents
        if intent.acquisition_intent_id == intent_id
    )
    if not matching_field_intents:
        return _not_eligible(
            intent_id,
            AcquisitionIntentEligibilityReason.INTENT_NOT_IN_IMAGING_FIELD,
        )
    if matching_field_intents != (acquisition_intent,):
        raise ValueError("acquisition_intent_definition_mismatch")

    if intent_id not in {
        target.acquisition_intent_id for target in project_targets
    }:
        return _not_eligible(
            intent_id,
            AcquisitionIntentEligibilityReason.INTENT_NOT_TARGETED_BY_PROJECT,
        )

    if remaining_progress is not None and remaining_progress.acquisition_intent_id != intent_id:
        raise ValueError("remaining_progress_intent_mismatch")
    if remaining_progress is not None and remaining_progress.completed:
        return _not_eligible(
            intent_id, AcquisitionIntentEligibilityReason.INTENT_TARGET_COMPLETED,
        )

    evidence_gaps: list[AcquisitionIntentEvidenceGap] = []
    if setup_filter_capabilities is None:
        evidence_gaps.append(
            AcquisitionIntentEvidenceGap.SETUP_CAPABILITIES_MISSING
        )
    elif (
        acquisition_intent.filter_type
        not in setup_filter_capabilities.available_filter_types
    ):
        return _not_eligible(
            intent_id,
            AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE,
        )

    if productive_window is None:
        evidence_gaps.append(
            AcquisitionIntentEvidenceGap.PRODUCTIVE_WINDOW_EVIDENCE_MISSING
        )
    elif (
        select_continuous_actionable_productive_window(
            productive_window,
            session_availability,
        )
        is None
    ):
        return _not_eligible(
            intent_id,
            AcquisitionIntentEligibilityReason.INSUFFICIENT_ACTIONABLE_PRODUCTIVE_WINDOW,
        )

    if (
        weather_trust_decision is None
        or weather_trust_decision.evidence_quality
        is not WeatherEvidenceQuality.SUFFICIENT
        or weather_trust_decision.admissibility
        is not WeatherDecisionAdmissibility.ADMISSIBLE
    ):
        evidence_gaps.append(
            AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT
        )

    if evidence_gaps:
        return AcquisitionIntentEligibilityAssessment(
            acquisition_intent_id=intent_id,
            status=AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE,
            blocking_reasons=(),
            evidence_gaps=tuple(evidence_gaps),
        )
    return AcquisitionIntentEligibilityAssessment(
        acquisition_intent_id=intent_id,
        status=AcquisitionIntentEligibilityStatus.ELIGIBLE,
        blocking_reasons=(),
        evidence_gaps=(),
    )
