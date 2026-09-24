import ast
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from decision.definitions.production_imaging_fields import (
    IMAGING_FIELD_DEFINITIONS,
)
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
    ImagingFieldComponent,
    ImagingFieldDefinition,
)
from decision.models.project_acquisition_intent_target import (
    ProjectAcquisitionIntentTarget,
)
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.services.acquisition_intent_eligibility import (
    evaluate_acquisition_intent_eligibility,
)
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


START = datetime(2026, 9, 20, 20, tzinfo=timezone.utc)
FIELD = IMAGING_FIELD_DEFINITIONS[0]
HA_INTENT, OIII_INTENT = FIELD.acquisition_intents
TARGETS = (
    ProjectAcquisitionIntentTarget("sh2-129_ha", 8.0),
    ProjectAcquisitionIntentTarget("ou4_oiii", 12.0),
)
CAPABILITIES = SetupFilterCapabilities("dual-narrowband", ("Ha", "OIII"))
TRUSTED_WEATHER = WeatherTrustDecision(
    evidence_quality=WeatherEvidenceQuality.SUFFICIENT,
    admissibility=WeatherDecisionAdmissibility.ADMISSIBLE,
    reasons=(),
)


def productive_window(minutes: int = 60) -> ProductiveWindowAssessment:
    hours = minutes / 60
    window = SimpleNamespace(
        start_hour=0.0,
        end_hour=hours,
        productivity=0.8,
        productive=True,
    )
    return ProductiveWindowAssessment(
        window_start=START,
        window_end=START + timedelta(minutes=minutes),
        recommended_hours=hours,
        expected_gain=0.0,
        productivity=SimpleNamespace(windows=(window,)),
    )


def evaluate(
    intent: AcquisitionIntent = HA_INTENT,
    *,
    field: ImagingFieldDefinition = FIELD,
    targets: tuple[ProjectAcquisitionIntentTarget, ...] = TARGETS,
    capabilities: SetupFilterCapabilities | None = CAPABILITIES,
    window: ProductiveWindowAssessment | None = None,
    availability: SessionAvailability | None = None,
    weather: WeatherTrustDecision | None = TRUSTED_WEATHER,
) -> AcquisitionIntentEligibilityAssessment:
    return evaluate_acquisition_intent_eligibility(
        acquisition_intent=intent,
        imaging_field=field,
        project_targets=targets,
        setup_filter_capabilities=capabilities,
        productive_window=productive_window() if window is None else window,
        session_availability=availability,
        weather_trust_decision=weather,
    )


def assert_not_eligible(
    assessment: AcquisitionIntentEligibilityAssessment,
    reason: AcquisitionIntentEligibilityReason,
) -> None:
    assert assessment.status is AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE
    assert assessment.blocking_reasons == (reason,)
    assert assessment.evidence_gaps == ()


def assert_insufficient(
    assessment: AcquisitionIntentEligibilityAssessment,
    *gaps: AcquisitionIntentEvidenceGap,
) -> None:
    assert (
        assessment.status
        is AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE
    )
    assert assessment.blocking_reasons == ()
    assert assessment.evidence_gaps == gaps


def test_all_v1_gates_pass_at_exactly_sixty_continuous_minutes():
    assessment = evaluate()

    assert assessment == AcquisitionIntentEligibilityAssessment(
        acquisition_intent_id="sh2-129_ha",
        status=AcquisitionIntentEligibilityStatus.ELIGIBLE,
        blocking_reasons=(),
        evidence_gaps=(),
    )


def test_intent_outside_field_is_not_eligible_with_exact_reason():
    other = AcquisitionIntent("other_ha", "Ha", ("sh2-129",), "Hα · Other")

    assert_not_eligible(
        evaluate(other),
        AcquisitionIntentEligibilityReason.INTENT_NOT_IN_IMAGING_FIELD,
    )


def test_intent_not_targeted_by_project_is_not_eligible():
    assert_not_eligible(
        evaluate(targets=(TARGETS[1],)),
        AcquisitionIntentEligibilityReason.INTENT_NOT_TARGETED_BY_PROJECT,
    )


def test_missing_setup_capabilities_is_insufficient_evidence():
    assert_insufficient(
        evaluate(capabilities=None),
        AcquisitionIntentEvidenceGap.SETUP_CAPABILITIES_MISSING,
    )


def test_required_filter_unavailable_is_not_eligible():
    assert_not_eligible(
        evaluate(
            capabilities=SetupFilterCapabilities("ha-only", ("OIII",)),
        ),
        AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE,
    )


def test_missing_productive_window_is_insufficient_evidence():
    assessment = evaluate_acquisition_intent_eligibility(
        acquisition_intent=HA_INTENT,
        imaging_field=FIELD,
        project_targets=TARGETS,
        setup_filter_capabilities=CAPABILITIES,
        productive_window=None,
        session_availability=None,
        weather_trust_decision=TRUSTED_WEATHER,
    )

    assert_insufficient(
        assessment,
        AcquisitionIntentEvidenceGap.PRODUCTIVE_WINDOW_EVIDENCE_MISSING,
    )


@pytest.mark.parametrize(
    ("window_start", "window_end"),
    (
        (None, None),
        (START, None),
        (START + timedelta(hours=1), START),
    ),
)
def test_missing_or_invalid_temporal_bounds_remain_insufficient_evidence(
    window_start,
    window_end,
):
    source = ProductiveWindowAssessment(
        window_start=window_start,
        window_end=window_end,
        recommended_hours=0,
        expected_gain=0,
        productivity=SimpleNamespace(windows=None),
    )

    assessment = evaluate(window=source)

    assert_insufficient(
        assessment,
        AcquisitionIntentEvidenceGap.PRODUCTIVE_WINDOW_EVIDENCE_MISSING,
    )


def test_known_productive_window_below_sixty_minutes_is_not_eligible():
    assert_not_eligible(
        evaluate(window=productive_window(59)),
        AcquisitionIntentEligibilityReason.INSUFFICIENT_ACTIONABLE_PRODUCTIVE_WINDOW,
    )


@pytest.mark.parametrize(
    ("quality", "admissibility"),
    (
        (WeatherEvidenceQuality.INSUFFICIENT, WeatherDecisionAdmissibility.CAUTION),
        (WeatherEvidenceQuality.INSUFFICIENT, WeatherDecisionAdmissibility.REFUSED),
        (WeatherEvidenceQuality.INVALID, WeatherDecisionAdmissibility.REFUSED),
    ),
)
def test_weather_trust_shortfall_is_only_an_evidence_gap(
    quality,
    admissibility,
):
    assessment = evaluate(
        weather=WeatherTrustDecision(quality, admissibility, ("trust_gap",)),
    )

    assert_insufficient(
        assessment,
        AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT,
    )


def test_provider_reliability_only_caution_continues_through_other_gates():
    assessment = evaluate(
        weather=WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.CAUTION,
            ("provider_reliability_unavailable",),
        ),
    )

    assert assessment.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
    assert assessment.blocking_reasons == ()
    assert assessment.evidence_gaps == ()


@pytest.mark.parametrize(
    ("quality", "admissibility"),
    (
        (WeatherEvidenceQuality.SUFFICIENT, WeatherDecisionAdmissibility.CAUTION),
        (WeatherEvidenceQuality.INSUFFICIENT, WeatherDecisionAdmissibility.ADMISSIBLE),
        (WeatherEvidenceQuality.INSUFFICIENT, WeatherDecisionAdmissibility.REFUSED),
        (WeatherEvidenceQuality.INVALID, WeatherDecisionAdmissibility.REFUSED),
    ),
)
def test_provider_reliability_reason_with_any_other_structured_state_is_blocking(
    quality,
    admissibility,
):
    assert_insufficient(
        evaluate(
            weather=WeatherTrustDecision(
                quality,
                admissibility,
                ("provider_reliability_unavailable",),
            ),
        ),
        AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT,
    )


@pytest.mark.parametrize(
    "reasons",
    (
        ("provider_reliability_unavailable", "weather_freshness_missing"),
        ("provider_report_scope_mismatch",),
        ("provider_context_not_evaluated",),
        ("provider_evidence_missing:cloud_cover",),
        ("provider_evidence_insufficient:cloud_cover",),
    ),
)
def test_other_or_additional_caution_reasons_remain_weather_evidence_gaps(
    reasons,
):
    assessment = evaluate(
        weather=WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.CAUTION,
            reasons,
        ),
    )

    assert_insufficient(
        assessment,
        AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT,
    )


@pytest.mark.parametrize(
    "weather",
    (
        None,
        WeatherTrustDecision(
            WeatherEvidenceQuality.INVALID,
            WeatherDecisionAdmissibility.REFUSED,
            ("invalid_weather_units",),
        ),
        WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.REFUSED,
            ("weather_snapshot_missing",),
        ),
        WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.REFUSED,
            ("weather_freshness_missing",),
        ),
        WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.REFUSED,
            ("weather_not_fresh",),
        ),
        WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.REFUSED,
            ("selected_window_uncovered",),
        ),
        WeatherTrustDecision(
            WeatherEvidenceQuality.INSUFFICIENT,
            WeatherDecisionAdmissibility.REFUSED,
            ("selected_window_coverage_unknown",),
        ),
    ),
)
def test_missing_invalid_stale_or_uncovered_current_weather_remains_blocking(
    weather,
):
    assert_insufficient(
        evaluate(weather=weather),
        AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT,
    )


def test_certain_failure_discards_earlier_and_later_evidence_gaps():
    assessment = evaluate_acquisition_intent_eligibility(
        acquisition_intent=HA_INTENT,
        imaging_field=FIELD,
        project_targets=TARGETS,
        setup_filter_capabilities=None,
        productive_window=productive_window(59),
        session_availability=None,
        weather_trust_decision=None,
    )

    assert_not_eligible(
        assessment,
        AcquisitionIntentEligibilityReason.INSUFFICIENT_ACTIONABLE_PRODUCTIVE_WINDOW,
    )


def test_user_availability_is_applied_by_existing_integrated_window_contract():
    availability = SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=START,
        end=START + timedelta(minutes=59),
    )

    assert_not_eligible(
        evaluate(window=productive_window(90), availability=availability),
        AcquisitionIntentEligibilityReason.INSUFFICIENT_ACTIONABLE_PRODUCTIVE_WINDOW,
    )


@pytest.mark.parametrize(
    "assessment",
    (
        lambda: AcquisitionIntentEligibilityAssessment(
            "intent",
            AcquisitionIntentEligibilityStatus.ELIGIBLE,
            (AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE,),
            (),
        ),
        lambda: AcquisitionIntentEligibilityAssessment(
            "intent",
            AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE,
            (),
            (),
        ),
        lambda: AcquisitionIntentEligibilityAssessment(
            "intent",
            AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE,
            (AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE,),
            (AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT,),
        ),
        lambda: AcquisitionIntentEligibilityAssessment(
            "intent",
            AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE,
            (),
            (),
        ),
        lambda: AcquisitionIntentEligibilityAssessment(
            "intent",
            AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE,
            (AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE,),
            (AcquisitionIntentEvidenceGap.WEATHER_EVIDENCE_INSUFFICIENT,),
        ),
    ),
)
def test_assessment_rejects_invalid_status_reason_gap_combinations(assessment):
    with pytest.raises(ValueError):
        assessment()


def test_contract_has_only_the_four_frozen_output_fields():
    assert tuple(field.name for field in fields(
        AcquisitionIntentEligibilityAssessment
    )) == (
        "acquisition_intent_id",
        "status",
        "blocking_reasons",
        "evidence_gaps",
    )


def test_evaluator_does_not_depend_on_progress_or_filter_selection():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "services"
        / "acquisition_intent_eligibility.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    source_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    source_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not {
        "ProjectFilterProgress",
        "remaining_hours_by_filter",
        "FilterSelectionEngine",
    } & (source_names | source_attributes)


def test_sh2_129_ou4_intents_can_both_be_eligible_without_a_winner():
    assessments = tuple(evaluate(intent) for intent in (OIII_INTENT, HA_INTENT))

    assert tuple(item.acquisition_intent_id for item in assessments) == (
        "ou4_oiii",
        "sh2-129_ha",
    )
    assert all(
        item.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
        for item in assessments
    )
