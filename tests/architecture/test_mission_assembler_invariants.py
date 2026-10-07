from dataclasses import replace
from dataclasses import FrozenInstanceError, fields
from datetime import timedelta
from types import SimpleNamespace

import pytest

import decision.mission.mission_assembler as module
from decision.mission.mission_assembler import (
    MissionAssembler,
    ProductiveWindowAssessment,
)
from decision.mission.mission_input import MissionInput
from decision.mission.night_mission import MissionReason
from decision.filtering.selected_filter import SelectedFilter
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.weather.weather_forecast import WeatherForecast
from decision.validation.decision_consistency import DecisionConsistencyGate


@pytest.fixture
def summary():
    return SimpleNamespace(
        positives=["Bonne altitude", "Projet prioritaire"],
        negatives=["Lune présente"],
        confidence=0.85,
    )


@pytest.fixture
def context(frozen_time, buttes_site):
    return SimpleNamespace(
        site=buttes_site,
        session=SimpleNamespace(
            start_time=frozen_time,
            end_time=frozen_time + timedelta(hours=4),
        ),
        weather=SimpleNamespace(
            cloud_cover=55.0,
            humidity=70.0,
            wind_speed_kmh=8.0,
            seeing_arcsec=1.8,
            temperature_c=5.0,
        ),
        sky=SimpleNamespace(target_altitude_deg=42.0),
    )


@pytest.fixture
def isolated_dependencies(monkeypatch):
    captured = {}
    productivity = SimpleNamespace(
        astronomical_hours=2.0,
        productive_hours=1.2,
        confidence=0.6,
        windows=[SimpleNamespace(
            start_hour=0.0,
            end_hour=1.5,
            productivity=0.8,
            productive=True,
        )],
        timeline=SimpleNamespace(slices=["slice"]),
    )
    risk = SimpleNamespace(level="LOW")
    season = SimpleNamespace(conclusion="favorable")
    image_quality = SimpleNamespace(score=8.0, confidence=1.0)
    astro_quality = SimpleNamespace(score=82.0)
    dew_risk = SimpleNamespace(score=60.0)
    tasks = [SimpleNamespace(title="Capture")]

    def evaluate_productivity(productivity_context):
        captured["productivity_context"] = productivity_context
        return productivity

    def evaluate_astro(astro_context):
        captured["astro_context"] = astro_context
        return astro_quality

    monkeypatch.setattr(
        module.NightProductivityEngine,
        "evaluate",
        evaluate_productivity,
    )
    monkeypatch.setattr(
        module.ProjectRiskContextBuilder,
        "build",
        lambda **kwargs: (
            captured.update(risk_kwargs=kwargs)
            or SimpleNamespace(**kwargs)
        ),
    )
    monkeypatch.setattr(module.RiskEngine, "evaluate", lambda value: risk)
    monkeypatch.setattr(module.NightPlanner, "build", lambda value: tasks)
    monkeypatch.setattr(
        module.ImageQualityEngine,
        "evaluate",
        lambda value: image_quality,
    )
    monkeypatch.setattr(
        module.AstroQualityEngine,
        "evaluate",
        evaluate_astro,
    )
    monkeypatch.setattr(
        module.DewRiskEngine,
        "evaluate",
        lambda **kwargs: dew_risk,
    )
    monkeypatch.setattr(
        module.SeasonAnalysis,
        "analyze",
        lambda value: season,
    )
    monkeypatch.setattr(
        module.DynamicSeasonEngine,
        "target_visibility_window",
        lambda *args: [],
    )

    return SimpleNamespace(
        captured=captured,
        productivity=productivity,
        risk=risk,
        season=season,
        astro_quality=astro_quality,
        dew_risk=dew_risk,
        tasks=tasks,
    )


def mission_input(frozen_time, weather, **overrides):
    values = {
        "availability": SessionAvailability(SessionAvailabilityMode.ALL_NIGHT),
        "window_start": frozen_time,
        "window_end": frozen_time + timedelta(hours=2),
        "astronomical_hours": 2.0,
        "weather": weather,
        "moon_penalty": 0.3,
        "recommended_hours": 1.5,
        "expected_gain": 4.5,
        "selected_filter": None,
    }
    values.update(overrides)
    return MissionInput(**values)


def test_mission_preserves_reasons_and_computed_results(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    selected_filter = object()
    input_data = mission_input(
        frozen_time,
        None,
        selected_filter=selected_filter,
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=["setup"],
        alternatives=[],
        mission_input=input_data,
    )

    assert mission.reasons == [
        MissionReason("Bonne altitude", "success"),
        MissionReason("Projet prioritaire", "success"),
        MissionReason("Lune présente", "warning"),
    ]
    assert mission.confidence == 0.85
    assert mission.window_start == input_data.window_start
    assert mission.window_end == input_data.window_start + timedelta(hours=1.5)
    assert mission.recommended_hours == 1.5
    assert mission.expected_gain == 3.6
    assert mission.selected_filter is selected_filter
    assert mission.productivity is isolated_dependencies.productivity


@pytest.mark.parametrize(
    ("intent_id", "filter_type"),
    [("sh2-129_ha", "OIII"), ("ou4_oiii", "Ha")],
)
def test_mission_rejects_filter_diverging_from_selected_intent(
    frozen_time,
    summary,
    context,
    intent_id,
    filter_type,
):
    input_data = mission_input(
        frozen_time,
        None,
        imaging_field_id="sh2-129_ou4",
        acquisition_intent_id=intent_id,
        selected_filter=SelectedFilter(filter_type, filter_type),
    )

    with pytest.raises(ValueError, match="selected_filter_intent_mismatch"):
        MissionAssembler.build(
            target="M31",
            summary=summary,
            context=context,
            equipment=["setup"],
            alternatives=[],
            mission_input=input_data,
        )


def test_eligible_intent_without_legacy_filter_remains_actionable(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=["setup"],
        alternatives=[],
        mission_input=mission_input(
            frozen_time,
            None,
            imaging_field_id="sh2-129_ou4",
            acquisition_intent_id="sh2-129_ha",
            selected_filter=None,
        ),
        _include_actionability_diagnostic=True,
    )

    assert result.mission is not None
    assert result.mission.selected_filter is None
    assert result.actionability_refusal is None


@pytest.mark.parametrize("imaging_field_id", [None, "sh2-129_ou4"])
def test_mission_copies_imaging_field_identity_exactly(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
    imaging_field_id,
):
    input_data = mission_input(
        frozen_time,
        None,
        imaging_field_id=imaging_field_id,
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=["setup"],
        alternatives=[],
        mission_input=input_data,
    )

    assert mission.imaging_field_id == imaging_field_id
    assert mission.risk_report is isolated_dependencies.risk
    assert mission.season_analysis is isolated_dependencies.season
    assert mission.tasks is isolated_dependencies.tasks
    assert mission.night_slices == ["slice"]
    assert mission.astro_quality is isolated_dependencies.astro_quality
    assert mission.dew_risk is isolated_dependencies.dew_risk
    assert (
        isolated_dependencies.captured["risk_kwargs"]["observation_time"]
        is input_data.window_start
    )


def test_mission_copies_acquisition_intent_identity_exactly(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    input_data = mission_input(
        frozen_time,
        None,
        acquisition_intent_id=" intent-A ",
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=["setup"],
        alternatives=[],
        mission_input=input_data,
    )

    assert mission.acquisition_intent_id == " intent-A "


def test_mission_preserves_unknown_summary_confidence(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    summary.confidence = None

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(frozen_time, None),
    )

    assert mission.confidence is None


def test_mission_input_weather_takes_precedence_over_explicit_weather(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    explicit_weather = WeatherForecast(hourly_clouds=[90.0])
    selected_weather = WeatherForecast(
        hourly_clouds=[10.0, 30.0],
        hourly_humidity=[60.0, 80.0],
        hourly_wind=[4.0, 8.0],
        hourly_seeing=[1.0, 1.4],
        hourly_temperature=[2.0, 6.0],
        hourly_moon_penalty=[0.3, 0.3],
    )

    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        weather=explicit_weather,
        mission_input=mission_input(frozen_time, selected_weather),
    )

    productivity_context = isolated_dependencies.captured[
        "productivity_context"
    ]
    assert productivity_context.weather is selected_weather
    assert productivity_context.cloud_cover == 20.0
    assert productivity_context.humidity == 70.0
    assert productivity_context.wind == 6.0
    assert productivity_context.seeing == 1.2


def test_window_duration_fills_missing_astronomical_hours(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    input_data = mission_input(
        frozen_time,
        None,
        astronomical_hours=None,
        window_end=frozen_time + timedelta(hours=2, minutes=30),
    )

    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=input_data,
    )

    productivity_context = isolated_dependencies.captured[
        "productivity_context"
    ]
    assert productivity_context.astronomical_hours == 2.5


def test_context_session_without_lunar_evidence_is_not_productive(
    summary, context, isolated_dependencies,
):
    result = MissionAssembler.build(
        target="M31", summary=summary, context=context, equipment=[], alternatives=[],
    )
    assert result is None
    assert "productivity_context" not in isolated_dependencies.captured


def test_missing_target_altitude_skips_astro_quality(
    monkeypatch,
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    context.sky.target_altitude_deg = None
    monkeypatch.setattr(
        module.AstroQualityEngine,
        "evaluate",
        lambda value: pytest.fail("astro quality must not be evaluated"),
    )

    mission = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(frozen_time, None),
    )

    assert mission.astro_quality is None


def test_build_does_not_mutate_context(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    original = {
        "start_time": context.session.start_time,
        "end_time": context.session.end_time,
        "cloud_cover": context.weather.cloud_cover,
        "humidity": context.weather.humidity,
        "wind_speed_kmh": context.weather.wind_speed_kmh,
        "seeing_arcsec": context.weather.seeing_arcsec,
        "temperature_c": context.weather.temperature_c,
        "target_altitude_deg": context.sky.target_altitude_deg,
    }

    MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(frozen_time, None),
    )

    assert {
        "start_time": context.session.start_time,
        "end_time": context.session.end_time,
        "cloud_cover": context.weather.cloud_cover,
        "humidity": context.weather.humidity,
        "wind_speed_kmh": context.weather.wind_speed_kmh,
        "seeing_arcsec": context.weather.seeing_arcsec,
        "temperature_c": context.weather.temperature_c,
        "target_altitude_deg": context.sky.target_altitude_deg,
    } == original


def test_mission_duration_uses_the_real_continuous_productive_window(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 0.75
    isolated_dependencies.productivity.windows = [SimpleNamespace(
        start_hour=0.0,
        end_hour=1.0,
        productivity=0.75,
        productive=True,
    )]
    input_data = mission_input(
        frozen_time,
        None,
        recommended_hours=1.5,
        expected_gain=6.0,
    )

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=input_data,
    )

    assert result.recommended_hours == 1.0
    assert result.expected_gain == 3.0


def test_expected_gain_is_unchanged_for_the_full_assessment_window(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 2.0
    isolated_dependencies.productivity.windows = [SimpleNamespace(
        start_hour=0.0,
        end_hour=2.0,
        productivity=0.8,
        productive=True,
    )]

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(
            frozen_time,
            None,
            recommended_hours=2.0,
            expected_gain=6.0,
        ),
    )

    assert result.recommended_hours == 2.0
    assert result.expected_gain == 6.0


def test_expected_gain_is_prorated_to_the_selected_actionable_hour(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 2.0
    isolated_dependencies.productivity.windows = [SimpleNamespace(
        start_hour=0.0,
        end_hour=2.0,
        productivity=0.8,
        productive=True,
    )]
    availability = SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=frozen_time,
        end=frozen_time + timedelta(hours=1),
    )

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(
            frozen_time,
            None,
            recommended_hours=2.0,
            expected_gain=6.0,
            availability=availability,
        ),
    )

    assert result.recommended_hours == 1.0
    assert result.expected_gain == 3.0
    assert result.expected_gain <= 6.0


def test_expected_gain_cannot_increase_when_selected_window_exceeds_gain_reference(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 1.0
    isolated_dependencies.productivity.windows = [SimpleNamespace(
        start_hour=0.0,
        end_hour=2.0,
        productivity=0.8,
        productive=True,
    )]

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(
            frozen_time,
            None,
            recommended_hours=2.0,
            expected_gain=6.0,
        ),
    )

    assert result.recommended_hours == 2.0
    assert result.expected_gain == 3.0


def test_zero_reference_duration_never_transports_expected_gain(
    frozen_time,
    isolated_dependencies,
):
    isolated_dependencies.productivity.windows = [SimpleNamespace(
        start_hour=0.0,
        end_hour=1.0,
        productivity=0.8,
        productive=True,
    )]
    assessment = ProductiveWindowAssessment(
        window_start=frozen_time,
        window_end=frozen_time + timedelta(hours=2),
        recommended_hours=0.0,
        expected_gain=6.0,
        productivity=isolated_dependencies.productivity,
    )

    timing = module._mission_timing_for_availability(assessment, SessionAvailability(SessionAvailabilityMode.ALL_NIGHT))

    assert timing is not None
    assert timing[2:] == (1.0, 0.0)


def test_no_productive_window_creates_no_mission(
    frozen_time,
    summary,
    context,
    isolated_dependencies,
):
    isolated_dependencies.productivity.productive_hours = 0.75
    isolated_dependencies.productivity.windows = []

    result = MissionAssembler.build(
        target="M31",
        summary=summary,
        context=context,
        equipment=[],
        alternatives=[],
        mission_input=mission_input(
            frozen_time,
            None,
            recommended_hours=1.5,
            expected_gain=6.0,
        ),
    )

    assert result is None


def test_productive_window_assessment_is_immutable_and_gate_compatible(
    frozen_time,
    context,
    isolated_dependencies,
):
    window = SimpleNamespace(
        start_hour=0.0,
        end_hour=1.0,
        productivity=0.8,
        productive=True,
    )
    productivity = isolated_dependencies.productivity
    productivity.astronomical_hours = 2.0
    productivity.productive_hours = 0.75
    productivity.confidence = 0.375
    productivity.windows = [window]
    input_data = mission_input(
        frozen_time,
        None,
        recommended_hours=1.5,
        expected_gain=6.0,
    )

    assessment = ProductiveWindowAssessment.build(
        target="M31",
        context=context,
        mission_input=input_data,
    )

    assert [field.name for field in fields(assessment)] == [
        "window_start",
        "window_end",
        "recommended_hours",
        "expected_gain",
        "productivity",
        "maximum_mission_hours",
        "productivity_breakdown",
        "acquisition_capacity",
        "evidence_issues",
    ]
    assert assessment.window_start is input_data.window_start
    assert assessment.window_end is input_data.window_end
    assert assessment.recommended_hours == 0.75
    assert assessment.expected_gain == 3.0
    assert assessment.productivity is productivity
    assert assessment.maximum_mission_hours == 1.5
    DecisionConsistencyGate.validate_mission(assessment)
    assert DecisionConsistencyGate.has_productive_window(assessment) is True
    with pytest.raises(FrozenInstanceError):
        assessment.recommended_hours = 2.0


def test_assessment_without_productive_window_is_consistent_but_ineligible(
    frozen_time,
    context,
    isolated_dependencies,
):
    productivity = isolated_dependencies.productivity
    productivity.astronomical_hours = 2.0
    productivity.productive_hours = 0.75
    productivity.confidence = 0.375
    productivity.windows = []

    assessment = ProductiveWindowAssessment.build(
        target="M31",
        context=context,
        mission_input=mission_input(
            frozen_time,
            None,
            recommended_hours=1.5,
            expected_gain=6.0,
        ),
    )

    assert assessment.recommended_hours == 0.0
    assert assessment.expected_gain == 0.0
    DecisionConsistencyGate.validate_mission(assessment)
    assert DecisionConsistencyGate.has_productive_window(assessment) is False


@pytest.mark.parametrize(
    ("intent_id", "required_type", "other_type"),
    [("sh2-129_ha", "Ha", "OIII"), ("ou4_oiii", "OIII", "Ha")],
)
@pytest.mark.parametrize("inventory_kind", ["absent", "incompatible", "compatible"])
@pytest.mark.parametrize("bandwidth_nm", [3.0, 7.0])
def test_tonight_composes_intent_filter_through_real_input_and_assembler(
    monkeypatch, frozen_time, summary, context, isolated_dependencies,
    intent_id, required_type, other_type, inventory_kind, bandwidth_nm,
):
    import astro_score
    from decision.services.tonight_mission_service import TonightMissionService

    compatible = SelectedFilter("Hardware", required_type, bandwidth_nm,
                                source="user_default")
    incompatible = SelectedFilter("Other", other_type)
    inventory = {
        "absent": (),
        "incompatible": (incompatible,),
        "compatible": (incompatible, compatible),
    }[inventory_kind]
    monkeypatch.setattr(astro_score.FilterInventoryLoader, "load", lambda: inventory)
    # Force the old heuristic to disagree: only the intent can authorize the type.
    monkeypatch.setattr(astro_score.FilterSelectionEngine, "select",
                        lambda _: incompatible)
    evaluation = {
        "catalog_key": "Sh2-129",
        "imaging_field_id": "sh2-129_ou4",
        "selected_acquisition_intent_id": intent_id,
        "window": {"start": frozen_time,
                   "end": frozen_time + timedelta(hours=2),
                   "moon_penalty": 0.2},
        "remaining_hours": 2.0,
    }
    inputs = []

    def build_input(value):
        result = astro_score.build_mission_input(value, profile={"projects": {"Sh2-129": {
            "imaging_field_id": "sh2-129_ou4",
            "acquisition_intent_targets": [{"acquisition_intent_id": intent_id, "target_hours": 2}],
            "acquisition_intent_progress": [{"acquisition_intent_id": intent_id, "acquired_duration_manual": 0}],
        }}})
        result = replace(result, availability=SessionAvailability(SessionAvailabilityMode.ALL_NIGHT))
        inputs.append(result)
        return result

    service = TonightMissionService(build_mission=lambda **kwargs:
        MissionAssembler.build(equipment=["setup"], alternatives=[], **kwargs))
    mission = service.create(
        winner={"object_evaluations": {"Sh2-129": evaluation}},
        objects=[{"catalog_key": "Sh2-129", "name": "Sh2-129",
                  "decision_summary": summary, "decision_context": context}],
        recommended_key="Sh2-129", build_mission_input=build_input,
    )
    expected = None  # A legacy type match is not an exact modern profile identity.
    assert inputs[0].selected_filter is expected
    assert mission.selected_filter is expected
    assert mission.imaging_field_id == inputs[0].imaging_field_id == "sh2-129_ou4"
    assert mission.acquisition_intent_id == inputs[0].acquisition_intent_id == intent_id
    if expected is not None:
        assert mission.selected_filter.bandwidth_nm == bandwidth_nm
        assert mission.selected_filter.source == "user_default"


@pytest.mark.parametrize("legacy_remaining", [0.0, 4.0])
@pytest.mark.parametrize("acquired", [0.5, 0.764, 1.0, 1.5, 2.0])
@pytest.mark.parametrize("user_hours", [None, 1.1])
def test_tonight_caps_duration_and_gain_by_intent_through_real_assembly(
    monkeypatch, frozen_time, summary, context, isolated_dependencies,
    legacy_remaining, acquired, user_hours,
):
    """Contradictory legacy totals cannot cap or expand an intent mission."""
    import astro_score
    from decision.definitions.production_imaging_fields import (
        build_production_imaging_field_resolver,
    )
    from decision.models.project_acquisition_intent_target import (
        ProjectAcquisitionIntentTarget,
    )
    from decision.services.acquisition_intent_remaining_progress import (
        derive_acquisition_intent_remaining_progress,
    )
    from decision.services.tonight_mission_service import TonightMissionService

    monkeypatch.setattr(astro_score.FilterInventoryLoader, "load", lambda: ())
    project = {
        "hours": 4.0 - legacy_remaining, "target_hours": 4.0,
        "imaging_field_id": "sh2-129_ou4",
        "acquisition_intent_targets": [
            {"acquisition_intent_id": "sh2-129_ha", "target_hours": 2.0},
        ],
        "acquisition_intent_progress": [
            {"acquisition_intent_id": "sh2-129_ha",
             "acquired_duration_manual": acquired * 3600},
        ],
    }
    remaining = derive_acquisition_intent_remaining_progress(
        build_production_imaging_field_resolver().resolve("sh2-129_ou4"),
        (ProjectAcquisitionIntentTarget("sh2-129_ha", 2.0),),
        tuple(project["acquisition_intent_progress"]),
    )[0]
    assert remaining.remaining_hours == pytest.approx(max(2 - acquired, 0))
    assert remaining.completed is (acquired >= 2)
    evaluation = {
        "catalog_key": "Sh2-129", "imaging_field_id": "sh2-129_ou4",
        "selected_acquisition_intent_id": "sh2-129_ha",
        "remaining_hours": astro_score.project_remaining_hours(
            "Sh2-129", {"Sh2-129": project},
        ),
        "window": {"start": frozen_time,
                   "end": frozen_time + timedelta(hours=2), "moon_penalty": 0},
    }
    service = TonightMissionService(build_mission=lambda **kwargs:
        MissionAssembler.build(equipment=["setup"], alternatives=[], **kwargs))
    def build_input(value):
        from dataclasses import replace
        result = astro_score.build_mission_input(value, profile={"projects": {"Sh2-129": project}})
        availability = (SessionAvailability(
            SessionAvailabilityMode.START_AND_DURATION, start=frozen_time,
            duration=timedelta(hours=user_hours),
        ) if user_hours is not None else SessionAvailability(SessionAvailabilityMode.ALL_NIGHT))
        return replace(result, availability=availability)

    mission = service.create(
        winner={"object_evaluations": {"Sh2-129": evaluation}},
        objects=[{"name": "Sh2-129", "catalog_key": "Sh2-129",
                  "decision_summary": summary, "decision_context": context}],
        recommended_key="Sh2-129",
        build_mission_input=build_input,
    )
    if remaining.remaining_hours < 1:
        assert mission is None
    else:
        expected_hours = min(1.5, remaining.remaining_hours, user_hours or 4)
        assert mission.recommended_hours == pytest.approx(expected_hours)
        assert mission.recommended_hours <= remaining.remaining_hours
        assert mission.recommended_hours <= (user_hours or 4)
        assert mission.expected_gain == round(expected_hours / 2 * 100, 2)


def test_assembler_carries_original_lunar_comparison_window_without_recalculation(
    frozen_time, summary, context, isolated_dependencies,
):
    from decision.models.intent_night_evidence import IntentNightEvidence
    from decision.models.lunar_contamination_estimate import LunarContaminationEstimate
    from decision.models.lunar_evidence_snapshot import LunarEvidenceSnapshot, IntentLunarEstimateSnapshot
    snapshot = LunarEvidenceSnapshot(
        IntentNightEvidence("sh2-129_ou4", frozen_time,
            frozen_time + timedelta(hours=4), 4, frozen_time, 0.8, 45, 50),
        tuple(IntentLunarEstimateSnapshot(intent, profile, wavelength, 6.5,
            LunarContaminationEstimate(profile, 0.3, rayleigh, mie))
            for intent, profile, wavelength, rayleigh, mie in (
                ("sh2-129_ha", "ha", 656.3, 1, 1),
                ("ou4_oiii", "oiii", 500.7, 2, 2))),
        "test-estimator", None)
    source = mission_input(frozen_time, None,
        imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha",
        lunar_evidence_snapshot=snapshot)
    mission = MissionAssembler.build(target="Sh2-129", summary=summary,
        context=context, equipment=["setup"], alternatives=[], mission_input=source)
    assert mission.lunar_evidence_snapshot is snapshot
    assert mission.window_end < snapshot.evidence.actionable_window_end


def test_mission_does_not_count_partial_image_setup_as_known_aqi(
    frozen_time, summary, context, isolated_dependencies, monkeypatch,
):
    monkeypatch.setattr(
        module.ImageQualityEngine, "evaluate",
        lambda value: SimpleNamespace(score=8.0, confidence=0.0),
    )
    mission = MissionAssembler.build(
        target="M31", summary=summary, context=context,
        equipment=["setup"], alternatives=[],
        mission_input=mission_input(frozen_time, None),
    )
    assert mission is not None
    assert isolated_dependencies.captured['astro_context'].image_quality_score is None


@pytest.mark.parametrize("source", ["inventory", "legacy_inventory", "selection", "user_default", "observed", "resolved_profile"])
def test_legacy_filter_cannot_authorize_modern_mission_at_real_assembler(
    frozen_time, summary, context, isolated_dependencies, source,
):
    selected = SelectedFilter("Old Ha", "Ha", 6.5, source=source)
    value = mission_input(frozen_time, None, selected_filter=selected,
                          imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha")
    # Construction is a historical read contract; authorization is a separate boundary.
    assert value.selected_filter is selected
    with pytest.raises(ValueError, match="legacy_filter_cannot_authorize_modern_mission"):
        MissionAssembler.build(target="M31", summary=summary, context=context,
                               equipment=[], alternatives=[], mission_input=value)
