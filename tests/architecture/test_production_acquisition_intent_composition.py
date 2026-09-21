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
):
    field = build_production_imaging_field_resolver().resolve("sh2-129_ou4")
    return compose_acquisition_intent_selection(
        imaging_field=field,
        project_targets=_targets(*targets),
        setup_filter_capabilities=capabilities,
        productive_window=productive_window or _productive_window(),
        session_availability=None,
        weather_trust_decision=weather or _weather(),
        site=SITE,
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
        {"weather": _weather(sufficient=False)},
    ],
)
def test_missing_critical_evidence_fails_closed(overrides):
    selection = _compose(**overrides)

    assert (
        selection.status
        is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT
    )
    assert selection.selected_acquisition_intent_id is None


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
    candidate = astro_score.recommend_project_for_night(
        _top_object(),
        available_hours=2.0,
        profile=_profile(project),
    ).candidates[0]

    assert candidate.imaging_field_id == project.get("imaging_field_id")
    assert candidate.selected_acquisition_intent_id is None
    assert candidate.viable_acquisition_intent_ids == ()
    assert candidate.acquisition_intent_selection_status is None


def test_modern_project_passes_exact_selection_without_changing_score(
    monkeypatch,
):
    expected = AcquisitionIntentSelection(
        selected_acquisition_intent_id="sh2-129_ha",
        viable_acquisition_intent_ids=("sh2-129_ha",),
        status=AcquisitionIntentSelectionStatus.PREFERRED,
        reason_codes=("UNIQUE_NON_DOMINATED_INTENT",),
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
    project = {
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
    assert candidate.decision_score == captured[0]["decision_score"]
