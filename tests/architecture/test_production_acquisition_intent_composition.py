from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import astro_score
from decision.definitions.production_filter_optical_profiles import (
    build_production_filter_optical_profile_resolver,
)
from decision.definitions.production_imaging_fields import (
    build_production_imaging_field_resolver,
)
from decision.definitions.production_setup_filter_capabilities import (
    SETUP_FILTER_CAPABILITIES,
)
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelection,
    AcquisitionIntentSelectionStatus,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment,
    AcquisitionIntentEligibilityReason,
    AcquisitionIntentEligibilityStatus,
    AcquisitionIntentEvidenceGap,
)
from decision.models.acquisition_intent_assessment import (
    AcquisitionIntentAssessment,
)
from decision.models.acquisition_intent_remaining_progress import (
    AcquisitionIntentRemainingProgress,
)
from decision.models.context.site_context import SiteContext
from decision.models.equipment.filter_optical_profile import FilterOpticalProfile
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.models.intent_night_evidence import IntentNightEvidence
from decision.models.lunar_contamination_estimate import (
    LunarContaminationEstimate,
)
from decision.models.project_acquisition_intent_target import (
    ProjectAcquisitionIntentTarget,
)
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.services.acquisition_intent_composition import (
    compose_acquisition_intent_selection,
)
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolver,
)
from decision.services.lunar_contamination_estimator import (
    LunarContaminationEstimator,
)
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


START = datetime(2026, 9, 1, 22, tzinfo=timezone.utc)
END = datetime(2026, 9, 2, 2, tzinfo=timezone.utc)
SITE = SiteContext("Mont Sujet", 47.12, 7.04, 1000.0, 4)


class FixedEvidenceBuilder:
    def __init__(self, *, moon_altitude_deg=45.0):
        self.moon_altitude_deg = moon_altitude_deg

    def build(self, **kwargs):
        return IntentNightEvidence(
            imaging_field_id=kwargs["imaging_field_id"],
            actionable_window_start=kwargs["actionable_window_start"],
            actionable_window_end=kwargs["actionable_window_end"],
            actionable_duration_hours=4.0,
            reference_time=START,
            moon_illumination=0.8,
            moon_altitude_deg=self.moon_altitude_deg,
            moon_separation_deg=50.0,
        )


class CrossingEstimator:
    def estimate(self, evidence, profile):
        values = {
            "baader_ha_highspeed_6_5nm": (1.0, 2.0),
            "baader_oiii_highspeed_6_5nm": (2.0, 1.0),
        }[profile.filter_profile_id]
        return LunarContaminationEstimate(
            filter_profile_id=profile.filter_profile_id,
            lunar_source_factor=1.0,
            rayleigh_relative_index=values[0],
            mie_relative_index=values[1],
        )


def _productive_window(hours=4.0):
    return ProductiveWindowAssessment(
        window_start=START,
        window_end=END,
        recommended_hours=hours,
        expected_gain=1.0,
        productivity=SimpleNamespace(
            windows=[SimpleNamespace(
                start_hour=0.0,
                end_hour=hours,
                productivity=0.9,
                productive=True,
            )]
        ),
        maximum_mission_hours=hours,
    )


def _weather(*, sufficient=True):
    return WeatherTrustDecision(
        evidence_quality=(
            WeatherEvidenceQuality.SUFFICIENT
            if sufficient
            else WeatherEvidenceQuality.INSUFFICIENT
        ),
        admissibility=(
            WeatherDecisionAdmissibility.ADMISSIBLE
            if sufficient
            else WeatherDecisionAdmissibility.CAUTION
        ),
        reasons=() if sufficient else ("provider_reliability_unavailable",),
    )


def _targets(*intent_ids):
    return tuple(
        ProjectAcquisitionIntentTarget(intent_id, 2.0)
        for intent_id in intent_ids
    )


def _compose(
    *,
    targets=("sh2-129_ha", "ou4_oiii"),
    capabilities=SETUP_FILTER_CAPABILITIES[0],
    productive_window=None,
    weather=None,
    profile_resolver=None,
    estimator=None,
    remaining_progress=None,
    site=SITE,
):
    field = build_production_imaging_field_resolver().resolve("sh2-129_ou4")
    if remaining_progress is None:
        remaining_progress = tuple(
            AcquisitionIntentRemainingProgress(intent_id, 0, 0, 2, 2)
            for intent_id in targets
        )
    return compose_acquisition_intent_selection(
        imaging_field=field,
        project_targets=_targets(*targets),
        remaining_progress=remaining_progress,
        setup_filter_capabilities=capabilities,
        productive_window=productive_window or _productive_window(),
        session_availability=None,
        weather_trust_decision=weather or _weather(),
        site=site,
        filter_profile_resolver=(
            profile_resolver or build_production_filter_optical_profile_resolver()
        ),
        evidence_builder=FixedEvidenceBuilder(),
        contamination_estimator=estimator or LunarContaminationEstimator(),
    )


def test_unique_eligible_intent_is_selected():
    selection = _compose(targets=("sh2-129_ha",))

    assert (
        selection.status
        is AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT
    )
    assert selection.selected_acquisition_intent_id == "sh2-129_ha"


def test_clear_lunar_dominance_is_propagated():
    selection = _compose()

    assert selection.status is AcquisitionIntentSelectionStatus.PREFERRED
    assert selection.selected_acquisition_intent_id == "sh2-129_ha"


def test_incomparable_lunar_evidence_keeps_complete_frontier():
    selection = _compose(estimator=CrossingEstimator())

    assert (
        selection.status
        is AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE
    )
    assert selection.selected_acquisition_intent_id is None
    assert selection.viable_acquisition_intent_ids == (
        "ou4_oiii",
        "sh2-129_ha",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"capabilities": None},
        {"productive_window": _productive_window(hours=0.5)},
    ],
)
def test_missing_critical_evidence_fails_closed(overrides):
    selection = _compose(**overrides)

    assert (
        selection.status
        is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT
    )
    assert selection.selected_acquisition_intent_id is None


def test_sh2_129_provider_reliability_caution_reaches_lunar_selection():
    selection = _compose(weather=_weather(sufficient=False))

    assert selection.status is AcquisitionIntentSelectionStatus.PREFERRED
    assert selection.selected_acquisition_intent_id == "sh2-129_ha"
    assert selection.viable_acquisition_intent_ids == ("sh2-129_ha",)
    assert [
        {
            "acquisition_intent_id": item.acquisition_intent_id,
            "filter_type": item.filter_type,
            "label": item.label,
            "status": item.status.value,
            "reason_codes": list(item.reason_codes),
        }
        for item in selection.acquisition_intent_assessments
    ] == [
        {
            "acquisition_intent_id": "sh2-129_ha",
            "filter_type": "Ha",
            "label": "Hα · Sh2-129",
            "status": "eligible",
            "reason_codes": [],
        },
        {
            "acquisition_intent_id": "ou4_oiii",
            "filter_type": "OIII",
            "label": "OIII · Ou4",
            "status": "eligible",
            "reason_codes": [],
        },
    ]


def test_revised_assessments_preserve_optical_and_lunar_evidence_gaps():
    optical = _compose(
        targets=("sh2-129_ha",),
        capabilities=SetupFilterCapabilities(
            "ambiguous",
            ("Ha",),
            ("ha-a", "ha-b"),
        ),
        profile_resolver=FilterOpticalProfileResolver((
            FilterOpticalProfile("ha-a", "Ha", 656.3, 6.5, True),
            FilterOpticalProfile("ha-b", "Ha", 656.3, 7.0, True),
        )),
    )
    lunar = _compose(site=None)

    assert optical.acquisition_intent_assessments[0].reason_codes == (
        AcquisitionIntentEvidenceGap.FILTER_PROFILE_EVIDENCE_INSUFFICIENT.value,
    )
    assert all(
        item.reason_codes
        == (AcquisitionIntentEvidenceGap.LUNAR_EVIDENCE_INSUFFICIENT.value,)
        for item in lunar.acquisition_intent_assessments
    )


def test_blocking_assessments_preserve_filter_unavailable_and_completion():
    capabilities = SetupFilterCapabilities(
        "ha-only",
        ("Ha",),
        ("baader_ha_highspeed_6_5nm",),
    )
    completed = AcquisitionIntentRemainingProgress(
        "sh2-129_ha", 7200.0, 2.0, 2.0, 0.0,
    )
    unknown = AcquisitionIntentRemainingProgress(
        "ou4_oiii", None, None, 2.0, None,
    )
    selection = _compose(
        capabilities=capabilities,
        remaining_progress=(completed, unknown),
    )
    assessments = {
        item.acquisition_intent_id: item
        for item in selection.acquisition_intent_assessments
    }

    assert assessments["sh2-129_ha"].status is (
        AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE
    )
    assert assessments["sh2-129_ha"].reason_codes == (
        AcquisitionIntentEligibilityReason.INTENT_TARGET_COMPLETED.value,
    )
    assert assessments["ou4_oiii"].reason_codes == (
        AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE.value,
    )


def test_ambiguous_filter_profile_is_never_chosen_arbitrarily():
    profiles = (
        FilterOpticalProfile("ha-a", "Ha", 656.3, 6.5, True),
        FilterOpticalProfile("ha-b", "Ha", 656.3, 7.0, True),
    )
    capabilities = SetupFilterCapabilities(
        equipment_id="ambiguous",
        available_filter_types=("Ha",),
        available_filter_profile_ids=("ha-a", "ha-b"),
    )

    selection = _compose(
        targets=("sh2-129_ha",),
        capabilities=capabilities,
        profile_resolver=FilterOpticalProfileResolver(profiles),
    )

    assert (
        selection.status
        is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT
    )


def _profile(project):
    return {
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
        "projects": {"Ou4": project},
    }


def _top_object():
    return [{
        "name": "Ou4",
        "catalog_key": "Ou4",
        "global_score": 80.0,
        "setup_score": 5.0,
        "best_setup": "samyang_183",
        "confidence": "HIGH",
    }]


@pytest.mark.parametrize(
    "project",
    [
        {"hours": 1.0, "target_hours": 4.0},
        {
            "hours": 1.0,
            "target_hours": 4.0,
            "imaging_field_id": "sh2-129_ou4",
        },
    ],
)
def test_legacy_project_keeps_absent_intent_provenance(
    monkeypatch,
    project,
):
    monkeypatch.setattr(
        astro_score.future_engine,
        "estimate",
        lambda *args, **kwargs: SimpleNamespace(risk="LOW", opportunity_ratio=1.0),
    )
    result = astro_score.recommend_project_for_night(
        _top_object(), available_hours=2.0, profile=_profile(project),
    )
    assert not result
    assert result.rejections[0].basis.value == "modern_provenance_missing"


def test_modern_project_passes_exact_selection_without_changing_score(
    monkeypatch,
):
    eligibility = AcquisitionIntentEligibilityAssessment(
        "sh2-129_ha",
        AcquisitionIntentEligibilityStatus.ELIGIBLE,
        (),
        (),
    )
    assessment = AcquisitionIntentAssessment(
        "sh2-129_ha",
        "Ha",
        "Hα · Sh2-129",
        AcquisitionIntentEligibilityStatus.ELIGIBLE,
        (),
    )
    expected = AcquisitionIntentSelection(
        selected_acquisition_intent_id="sh2-129_ha",
        viable_acquisition_intent_ids=("sh2-129_ha",),
        status=AcquisitionIntentSelectionStatus.PREFERRED,
        reason_codes=("UNIQUE_NON_DOMINATED_INTENT",),
        eligibility_assessments=(eligibility,),
        acquisition_intent_assessments=(assessment,),
    )
    captured = []
    original_build = astro_score.project_selection_engine.build_candidate

    monkeypatch.setattr(
        astro_score.future_engine,
        "estimate",
        lambda *args, **kwargs: SimpleNamespace(risk="LOW", opportunity_ratio=1.0),
    )
    monkeypatch.setattr(
        astro_score,
        "compose_acquisition_intent_selection",
        lambda **kwargs: expected,
    )

    def recording_build(**kwargs):
        captured.append(kwargs.copy())
        return original_build(**kwargs)

    monkeypatch.setattr(
        astro_score.project_selection_engine,
        "build_candidate",
        recording_build,
    )
    project = {"acquisition_intent_progress": [],
        "hours": 1.0,
        "target_hours": 4.0,
        "imaging_field_id": "sh2-129_ou4",
        "acquisition_intent_targets": [
            {"acquisition_intent_id": "sh2-129_ha", "target_hours": 2.0},
            {"acquisition_intent_id": "ou4_oiii", "target_hours": 2.0},
        ],
    }
    candidate = astro_score.recommend_project_for_night(
        _top_object(),
        available_hours=2.0,
        profile=_profile(project),
    ).candidates[0]

    assert captured[0]["acquisition_intent_selection"] is expected
    assert candidate.selected_acquisition_intent_id == "sh2-129_ha"
    assert candidate.acquisition_intent_assessments is (
        expected.acquisition_intent_assessments
    )
    assert candidate.decision_score == captured[0]["decision_score"]


def test_characterize_different_lunar_estimates_leave_identical_selection():
    """Regression: changed estimates remain visible with unchanged selection."""
    from dataclasses import replace

    class RecordingEstimator:
        def __init__(self, scale):
            self.scale = scale
            self.estimates = []

        def estimate(self, evidence, profile):
            estimate = LunarContaminationEstimator().estimate(evidence, profile)
            estimate = replace(
                estimate,
                rayleigh_relative_index=estimate.rayleigh_relative_index * self.scale,
                mie_relative_index=estimate.mie_relative_index * self.scale,
            )
            self.estimates.append(estimate)
            return estimate

    original = RecordingEstimator(1.0)
    changed = RecordingEstimator(2.0)
    first = _compose(estimator=original)
    second = _compose(estimator=changed)
    assert original.estimates != changed.estimates
    assert first.status is AcquisitionIntentSelectionStatus.PREFERRED
    assert replace(first, lunar_evidence_snapshot=None) == replace(second, lunar_evidence_snapshot=None)
    assert first.lunar_evidence_snapshot != second.lunar_evidence_snapshot


def test_short_intent_is_excluded_and_existing_selection_can_choose_other():
    selection = _compose(remaining_progress=(
        AcquisitionIntentRemainingProgress("sh2-129_ha", 5400, 1.5, 2, 0.5),
        AcquisitionIntentRemainingProgress("ou4_oiii", 0, 0, 2, 2),
    ))
    assert selection.selected_acquisition_intent_id == "ou4_oiii"
    assert selection.acquisition_intent_assessments[0].reason_codes == (
        "insufficient_actionable_productive_window",
    )


def test_unknown_remaining_cannot_be_selected():
    selection = _compose(targets=("sh2-129_ha",), remaining_progress=(
        AcquisitionIntentRemainingProgress("sh2-129_ha", None, None, 2, None),
    ))
    assert selection.selected_acquisition_intent_id is None
    assert selection.acquisition_intent_assessments[0].reason_codes == (
        "intent_progress_evidence_insufficient",
    )


def test_modern_ranking_gain_and_future_ignore_contradictory_legacy_totals(monkeypatch):
    selected = _compose(targets=("sh2-129_ha",), remaining_progress=(
        AcquisitionIntentRemainingProgress("sh2-129_ha", 1800, 0.5, 2, 1.5),
    ))
    monkeypatch.setattr(astro_score, "compose_acquisition_intent_selection", lambda **kwargs: selected)
    future_caps = []

    def future(*args, **kwargs):
        future_caps.append(kwargs["remaining_hours"])
        return SimpleNamespace(risk="LOW", opportunity_ratio=1)

    monkeypatch.setattr(astro_score.future_engine, "estimate", future)
    scores = []
    for legacy_hours in (0, 4):
        project = {
            "hours": legacy_hours, "target_hours": 4,
            "imaging_field_id": "sh2-129_ou4",
            "acquisition_intent_targets": [
                {"acquisition_intent_id": "sh2-129_ha", "target_hours": 2},
            ],
            "acquisition_intent_progress": [
                {"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 1800},
            ],
        }
        candidate = astro_score.recommend_project_for_night(
            _top_object(), available_hours=2, profile=_profile(project),
        ).candidates[0]
        scores.append((candidate.decision_score, candidate.strategy_scores))
    assert future_caps == [1.5, 1.5]
    assert scores[0] == scores[1]


class ScaledEstimator(LunarContaminationEstimator):
    def __init__(self, scale):
        self.scale = scale

    def estimate(self, evidence, profile):
        from dataclasses import replace
        estimate = super().estimate(evidence, profile)
        return replace(estimate,
            rayleigh_relative_index=estimate.rayleigh_relative_index * self.scale,
            mie_relative_index=estimate.mie_relative_index * self.scale)


def test_lunar_snapshot_distinguishes_same_winner_and_keeps_alternatives():
    first = _compose(estimator=ScaledEstimator(1))
    second = _compose(estimator=ScaledEstimator(2))
    assert first.selected_acquisition_intent_id == second.selected_acquisition_intent_id
    assert first.status == second.status
    assert first.reason_codes == second.reason_codes
    assert first.lunar_evidence_snapshot != second.lunar_evidence_snapshot
    snapshot = first.lunar_evidence_snapshot
    assert {item.acquisition_intent_id for item in snapshot.estimates} == {"sh2-129_ha", "ou4_oiii"}
    assert {item.estimate.filter_profile_id for item in snapshot.estimates} == {
        "baader_ha_highspeed_6_5nm", "baader_oiii_highspeed_6_5nm"}
    assert snapshot.evidence.reference_time == START
    assert snapshot.evidence.actionable_window_end == END
    assert snapshot.evidence.moon_separation_deg == 50


def test_single_intent_has_no_historical_lunar_snapshot():
    assert _compose(targets=("sh2-129_ha",)).lunar_evidence_snapshot is None


def test_incomparable_lunar_snapshot_keeps_both_estimates():
    selection = _compose(estimator=CrossingEstimator())
    assert selection.status is AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE
    assert len(selection.lunar_evidence_snapshot.estimates) == 2


def _snapshot_candidate():
    from decision.engines.project_selection_engine import ProjectSelectionEngine
    selection = _compose()
    return ProjectSelectionEngine.build_candidate(
        name="Sh2-129", catalog_key="Sh2-129", priority=1,
        astro_score=80, final_score=90, decision_score=80, portfolio_score=0,
        global_score=80, setup_score=80, best_setup="widefield",
        closure_bonus=0, reasons=[], strategy_scores={}, acquired_hours=0,
        imaging_field_id="sh2-129_ou4", acquisition_intent_selection=selection)


def test_candidate_mission_and_api_snapshot_round_trip_exactly():
    from dataclasses import asdict
    from decision.acceptance_lineage_persistence import _encode, _decode
    from decision.mission.mission_input import MissionInput
    from decision.mission.night_mission import NightMission
    from astropilot.app import _accepted_mission_response, TonightResponseModel
    from pydantic import TypeAdapter
    from decision.models.lunar_evidence_snapshot import LunarEvidenceSnapshot
    from decision.services.tonight_response import TonightResponse, _json_value
    candidate = _snapshot_candidate()
    snapshot = candidate.lunar_evidence_snapshot
    restored = _decode(_encode(candidate))
    assert restored.lunar_evidence_snapshot == snapshot
    source = MissionInput(START, END, 4, None, None, 2, 100,
        imaging_field_id=candidate.imaging_field_id,
        acquisition_intent_id=candidate.selected_acquisition_intent_id,
        lunar_evidence_snapshot=snapshot)
    assert _decode(_encode(source)).lunar_evidence_snapshot == snapshot
    mission = NightMission(target="Sh2-129", confidence=None,
        mission_id="mission", decision_id="decision", selection_id="selection",
        equipment=["widefield"], site_name="Mont Sujet",
        imaging_field_id=candidate.imaging_field_id,
        acquisition_intent_id=candidate.selected_acquisition_intent_id,
        lunar_evidence_snapshot=snapshot)
    restored_mission = _decode(_encode(mission))
    assert restored_mission.lunar_evidence_snapshot == snapshot
    expected = TypeAdapter(LunarEvidenceSnapshot).dump_python(snapshot, mode="json")
    assert _accepted_mission_response(restored_mission).model_dump(mode="json")["lunar_evidence_snapshot"] == expected
    response = TonightResponse(status="available", lunar_evidence_snapshot=snapshot)
    assert TonightResponseModel.model_validate(response.to_dict()).model_dump(mode="json")["lunar_evidence_snapshot"] == expected


@pytest.mark.parametrize("model", ["candidate", "mission_input", "mission"])
def test_v9_snapshot_absence_is_explicit_and_never_recomputed(model):
    from decision.acceptance_lineage_persistence import _encode, _decode
    from decision.mission.mission_input import MissionInput
    from decision.mission.night_mission import NightMission
    values = {
        "candidate": _snapshot_candidate(),
        "mission_input": MissionInput(START, END, 4, None, None, 2, 100),
        "mission": NightMission(target="Sh2-129", confidence=None),
    }
    document = _encode(values[model])
    document["fields"].pop("lunar_evidence_snapshot")
    assert _decode(document, schema_version=9).lunar_evidence_snapshot is None
    assert "lunar_evidence_snapshot" not in document["fields"]


def test_snapshot_rejects_profile_field_intent_and_eligible_set_mismatches():
    from dataclasses import replace, FrozenInstanceError
    candidate = _snapshot_candidate()
    snapshot = candidate.lunar_evidence_snapshot
    with pytest.raises(ValueError, match="profile_mismatch"):
        replace(snapshot.estimates[0], filter_profile_id="wrong-profile")
    with pytest.raises(ValueError, match="field_mismatch"):
        replace(candidate, imaging_field_id="wrong-field")
    with pytest.raises(ValueError, match="eligible_intents_mismatch"):
        replace(candidate, lunar_evidence_snapshot=replace(snapshot,
            estimates=(replace(snapshot.estimates[0], acquisition_intent_id="wrong-intent"), snapshot.estimates[1])))
    from decision.mission.mission_input import MissionInput
    with pytest.raises(ValueError, match="intent_mismatch"):
        MissionInput(START, END, 4, None, None, 2, 100,
            imaging_field_id=candidate.imaging_field_id,
            acquisition_intent_id="wrong-intent", lunar_evidence_snapshot=snapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.estimates[0].fwhm_nm = 999


def test_lunar_transport_does_not_change_candidate_ranking():
    from dataclasses import replace
    from decision.engines.project_selection_engine import ProjectSelectionEngine
    candidate = _snapshot_candidate()
    weaker = replace(candidate, catalog_key="weaker", final_score=70)
    assert [item.catalog_key for item in ProjectSelectionEngine.rank_candidates([weaker, candidate])] == [
        item.catalog_key for item in ProjectSelectionEngine.rank_candidates([
            replace(weaker, lunar_evidence_snapshot=None), replace(candidate, lunar_evidence_snapshot=None)])]


@pytest.mark.parametrize("tamper", [False, True])
def test_acceptance_copies_historical_candidate_snapshot_and_rejects_replacement(tamper):
    from dataclasses import replace
    from decision.mission.mission_input import MissionInput
    from decision.mission.night_mission import NightMission
    from decision.models.user_selection import UserSelection, UserSelectionSource
    from decision.recommendation.recommendation import Recommendation
    from decision.services.user_selection_mission import UserSelectionMissionService
    from decision.services.user_selection_validator import UserSelectionDecisionContext, UserSelectionValidationError
    candidate = _snapshot_candidate()
    snapshot = candidate.lunar_evidence_snapshot
    captured = []

    class MissionService:
        def create(self, **kwargs):
            source = kwargs["build_mission_input"](kwargs["winner"]["object_evaluations"][candidate.catalog_key])
            captured.append(source)
            return NightMission(target=candidate.catalog_key, confidence=None,
                mission_id=source.mission_id, decision_id=source.decision_id,
                selection_id=source.selection_id, site_name="Mont Sujet",
                equipment=["widefield"], imaging_field_id=source.imaging_field_id,
                acquisition_intent_id=source.acquisition_intent_id,
                lunar_evidence_snapshot=None if tamper else source.lunar_evidence_snapshot)

    service = UserSelectionMissionService(tonight_mission_service=MissionService(),
        build_mission_input=lambda *args, **kwargs: MissionInput(START, END, 4, None, None, 2, 100))
    kwargs = dict(availability=SessionAvailability(SessionAvailabilityMode.ALL_NIGHT), mission_id="mission", selection=UserSelection(
        selection_id="selection", decision_id="decision", selected_catalog_key=candidate.catalog_key,
        source=UserSelectionSource.PRIMARY_RECOMMENDATION, selected_at=START,
        selected_imaging_field_id=candidate.imaging_field_id,
        selected_acquisition_intent_id=candidate.selected_acquisition_intent_id),
        decision_context=UserSelectionDecisionContext("decision", candidate.catalog_key, (), (candidate.catalog_key,)),
        recommendation=Recommendation(SimpleNamespace(candidate=candidate), 0.9),
        night={"top_objects": [{"catalog_key": candidate.catalog_key}],
            "object_evaluations": {candidate.catalog_key: {
                "decision_context": SimpleNamespace(site=SITE),
                "lunar_evidence_snapshot": None}}}, profile={})
    if tamper:
        with pytest.raises(UserSelectionValidationError, match="mission_lunar_snapshot_mismatch"):
            service.create(**kwargs)
    else:
        mission = service.create(**kwargs)
        assert mission.lunar_evidence_snapshot is snapshot
    assert captured[0].lunar_evidence_snapshot is snapshot


def test_persistence_rejects_corrupt_snapshot_profile_identity():
    from decision.acceptance_lineage_persistence import _encode, _decode, AcceptanceLineageCorruptionError
    document = _encode(_snapshot_candidate())
    document["fields"]["lunar_evidence_snapshot"]["fields"]["estimates"]["items"][0]["fields"]["filter_profile_id"] = "wrong"
    with pytest.raises(AcceptanceLineageCorruptionError, match="invalid_dataclass_value"):
        _decode(document)


def test_alternative_api_transports_all_compared_intents():
    from dataclasses import replace
    from decision.recommendation.recommendation import Recommendation
    from decision.opportunity.opportunity import Opportunity
    from decision.opportunity.action import Action
    from decision.services.tonight_application_service import TonightResult
    from decision.services.tonight_response import TonightResponse
    from astropilot.app import TonightResponseModel
    from pydantic import TypeAdapter
    from decision.models.lunar_evidence_snapshot import LunarEvidenceSnapshot
    candidate = _snapshot_candidate()
    primary = replace(candidate, catalog_key="primary")
    result = TonightResult(night={"date": START.date()}, recommendation=Recommendation(
        Opportunity(action=Action.START_PROJECT, candidate=primary, shortlist_entries=(candidate,)), None), mission=None)
    response = TonightResponse.from_result(result, selected_alternatives=(candidate,)).to_dict()
    payload = TonightResponseModel.model_validate(response).model_dump(mode="json")
    assert payload["alternatives"][0]["lunar_evidence_snapshot"] == TypeAdapter(LunarEvidenceSnapshot).dump_python(candidate.lunar_evidence_snapshot, mode="json")


@pytest.mark.parametrize('equipment_id', [None, 'legacy_synthetic_setup'])
def test_legacy_inventory_and_synthetic_setup_do_not_supply_modern_capabilities(
    tmp_path, monkeypatch, equipment_id,
):
    import json
    from decision.filtering.filter_inventory_loader import FilterInventoryLoader
    from decision.services.setup_filter_capabilities_resolver import SetupFilterCapabilitiesResolutionError

    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    (tmp_path / 'user_filters.json').write_text(json.dumps({'filters': [
        {'name': 'Old Ha', 'type': 'Ha', 'bandwidth_nm': 6.5},
    ]}))
    assert FilterInventoryLoader.load()[0].filter_type == 'Ha'
    with pytest.raises(SetupFilterCapabilitiesResolutionError):
        astro_score.setup_filter_capabilities_resolver.resolve(equipment_id)
    result = _compose(targets=('sh2-129_ha',), capabilities=None)
    assert result.selected_acquisition_intent_id is None
    assert all(a.status is not AcquisitionIntentEligibilityStatus.ELIGIBLE for a in result.eligibility_assessments)


def test_same_type_legacy_inventory_does_not_replace_missing_optical_profile(tmp_path, monkeypatch):
    import json
    from decision.filtering.filter_inventory_loader import FilterInventoryLoader
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    (tmp_path / 'user_filters.json').write_text(json.dumps({'filters': [
        {'name': 'Old Ha', 'type': 'Ha', 'bandwidth_nm': 6.5},
    ]}))
    assert FilterInventoryLoader.load()[0].filter_type == 'Ha'
    result = _compose(targets=('sh2-129_ha',),
                      capabilities=SetupFilterCapabilities('modern', ('Ha',), ()))
    assert result.selected_acquisition_intent_id is None
    assert result.eligibility_assessments[0].status is AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE


def test_removing_exact_modern_profile_cannot_improve_intent_actionability():
    known = _compose(targets=('sh2-129_ha',))
    unknown = _compose(targets=('sh2-129_ha',),
                       capabilities=SetupFilterCapabilities('legacy', ('Ha',), ()))
    assert known.selected_acquisition_intent_id == 'sh2-129_ha'
    assert unknown.selected_acquisition_intent_id is None
