"""Production composition of first-class acquisition-intent decisions."""

from itertools import combinations

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment,
    AcquisitionIntentEligibilityStatus,
    AcquisitionIntentEvidenceGap,
)
from decision.models.acquisition_intent_filter_profile_resolution import (
    AcquisitionIntentFilterProfileResolutionStatus,
)
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelection,
)
from decision.models.context.site_context import SiteContext
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.models.imaging_field import ImagingFieldDefinition
from decision.models.project_acquisition_intent_target import (
    ProjectAcquisitionIntentTarget,
)
from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress
from decision.models.session_availability import SessionAvailability
from decision.services.acquisition_intent_eligibility import (
    evaluate_acquisition_intent_eligibility,
)
from decision.services.acquisition_intent_filter_profile_resolution import (
    AcquisitionIntentFilterProfileResolutionError,
    resolve_acquisition_intent_filter_profile,
)
from decision.services.acquisition_intent_preference import (
    determine_acquisition_intent_preference,
)
from decision.services.acquisition_intent_selection import (
    select_acquisition_intent,
)
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolutionError,
    FilterOpticalProfileResolver,
)
from decision.services.intent_night_evidence_builder import (
    IntentNightEvidenceBuildError,
    IntentNightEvidenceBuilder,
)
from decision.services.lunar_contamination_comparison import (
    compare_lunar_contamination,
)
from decision.services.lunar_contamination_estimator import (
    LunarContaminationEstimationError,
    LunarContaminationEstimator,
)
from decision.services.session_availability_windowing import (
    select_continuous_actionable_productive_window,
)
from decision.weather.weather_trust_decision import WeatherTrustDecision


def _insufficient(
    assessment: AcquisitionIntentEligibilityAssessment,
    gap: AcquisitionIntentEvidenceGap,
) -> AcquisitionIntentEligibilityAssessment:
    return AcquisitionIntentEligibilityAssessment(
        acquisition_intent_id=assessment.acquisition_intent_id,
        status=AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE,
        blocking_reasons=(),
        evidence_gaps=(gap,),
    )


def compose_acquisition_intent_selection(
    *,
    imaging_field: ImagingFieldDefinition,
    project_targets: tuple[ProjectAcquisitionIntentTarget, ...],
    remaining_progress: tuple[AcquisitionIntentRemainingProgress, ...] = (),
    setup_filter_capabilities: SetupFilterCapabilities | None,
    productive_window: ProductiveWindowAssessment | None,
    session_availability: SessionAvailability | None,
    weather_trust_decision: WeatherTrustDecision | None,
    site: SiteContext | None,
    filter_profile_resolver: FilterOpticalProfileResolver,
    evidence_builder: IntentNightEvidenceBuilder,
    contamination_estimator: LunarContaminationEstimator,
) -> AcquisitionIntentSelection:
    """Compose eligibility, lunar preference, and final selection.

    Any missing first-class profile or lunar evidence removes that intent from
    the eligible set. No comparison or preference is synthesized.
    """

    assessments = tuple(
        evaluate_acquisition_intent_eligibility(
            acquisition_intent=intent,
            imaging_field=imaging_field,
            project_targets=project_targets,
            remaining_progress=next((item for item in remaining_progress if item.acquisition_intent_id == intent.acquisition_intent_id), None),
            setup_filter_capabilities=setup_filter_capabilities,
            productive_window=productive_window,
            session_availability=session_availability,
            weather_trust_decision=weather_trust_decision,
        )
        for intent in imaging_field.acquisition_intents
    )
    if not any(
        assessment.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
        for assessment in assessments
    ):
        return select_acquisition_intent(assessments, ())

    intents_by_id = {
        intent.acquisition_intent_id: intent
        for intent in imaging_field.acquisition_intents
    }
    resolved_profile_ids: dict[str, str] = {}
    revised_assessments = []
    for assessment in assessments:
        if assessment.status is not AcquisitionIntentEligibilityStatus.ELIGIBLE:
            revised_assessments.append(assessment)
            continue
        intent = intents_by_id[assessment.acquisition_intent_id]
        try:
            resolution = resolve_acquisition_intent_filter_profile(
                intent,
                setup_filter_capabilities,
                filter_profile_resolver,
            )
        except AcquisitionIntentFilterProfileResolutionError:
            resolution = None
        if (
            resolution is None
            or resolution.status
            is not AcquisitionIntentFilterProfileResolutionStatus.RESOLVED
        ):
            revised_assessments.append(
                _insufficient(
                    assessment,
                    AcquisitionIntentEvidenceGap.FILTER_PROFILE_EVIDENCE_INSUFFICIENT,
                )
            )
            continue
        resolved_profile_ids[assessment.acquisition_intent_id] = (
            resolution.matching_filter_profile_ids[0]
        )
        revised_assessments.append(assessment)
    assessments = tuple(revised_assessments)

    eligible_ids = tuple(
        assessment.acquisition_intent_id
        for assessment in assessments
        if assessment.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
    )
    if not eligible_ids:
        return select_acquisition_intent(assessments, ())
    if len(eligible_ids) == 1:
        return select_acquisition_intent(assessments, ())

    actionable_window = (
        select_continuous_actionable_productive_window(
            productive_window,
            session_availability,
        )
        if productive_window is not None
        else None
    )
    if actionable_window is None or site is None:
        assessments = tuple(
            _insufficient(
                assessment,
                AcquisitionIntentEvidenceGap.LUNAR_EVIDENCE_INSUFFICIENT,
            )
            if assessment.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
            else assessment
            for assessment in assessments
        )
        return select_acquisition_intent(assessments, ())

    try:
        evidence = evidence_builder.build(
            imaging_field_id=imaging_field.imaging_field_id,
            actionable_window_start=actionable_window.window_start,
            actionable_window_end=actionable_window.window_end,
            site=site,
        )
        estimates = {
            intent_id: contamination_estimator.estimate(
                evidence,
                filter_profile_resolver.resolve(
                    resolved_profile_ids[intent_id]
                ),
            )
            for intent_id in eligible_ids
        }
    except (
        FilterOpticalProfileResolutionError,
        IntentNightEvidenceBuildError,
        LunarContaminationEstimationError,
    ):
        assessments = tuple(
            _insufficient(
                assessment,
                AcquisitionIntentEvidenceGap.LUNAR_EVIDENCE_INSUFFICIENT,
            )
            if assessment.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
            else assessment
            for assessment in assessments
        )
        return select_acquisition_intent(assessments, ())

    preferences = tuple(
        determine_acquisition_intent_preference(
            left_id,
            right_id,
            compare_lunar_contamination(
                estimates[left_id],
                estimates[right_id],
            ),
        )
        for left_id, right_id in combinations(sorted(eligible_ids), 2)
    )
    return select_acquisition_intent(assessments, preferences)
