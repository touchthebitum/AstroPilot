from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import decision.services.tonight_application_service as tonight_service_module
import decision.mission.mission_assembler as mission_assembler_module
import decision.services.session_availability_windowing as availability_windowing

from astropilot.user_profile import UserProfileError
from decision.forecast.forecast_run import ForecastRun
from decision.mission.night_mission import NightMission
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.mission.mission_input import MissionInput
from decision.night_productivity.night_productivity_result import NightProductivityResult
from decision.night_productivity.night_window import NightWindow
from decision.models.candidate import Candidate
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.tonight_application_service import (
    TonightApplicationService,
    TonightResult,
    TonightStatus,
    resolve_tonight_equipment,
    resolve_tonight_inputs,
)
from decision.models.candidate_rejection import (
    CandidateBuildResult,
    CandidateRejection,
    CandidateRejectionBasis,
)
from decision.models.candidate import CandidateProvenance
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


FORECAST_EVIDENCE = DecisionForecastEvidence(())
REFERENCE_TIME = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)


def make_profile(*, available_equipment=None, active_equipment="samyang_183"):
    return {
        "location": {"name": "Mont Sujet", "latitude": 47.12, "longitude": 7.04},
        "active_equipment": active_equipment,
        "available_equipment": available_equipment or [active_equipment],
    }


def test_tonight_equipment_resolver_accepts_valid_custom_identity():
    profile = make_profile(
        available_equipment=["custom_fra300"],
        active_equipment="custom_fra300",
    )
    profile["equipment_definitions"] = {
        "custom_fra300": {
            "optics_manufacturer": "Askar",
            "optics_model": "FRA300",
            "focal_length_mm": 300,
            "aperture_mm": 60,
            "f_ratio": 5,
            "camera_manufacturer": "ZWO",
            "camera_model": "ASI533MM",
            "pixel_size_um": 3.76,
            "sensor_width_px": 3008,
            "sensor_height_px": 3008,
            "monochrome": True,
        }
    }

    assert resolve_tonight_equipment(profile, None) == "custom_fra300"


def test_tonight_equipment_resolver_rejects_invalid_custom_definition():
    profile = make_profile(
        available_equipment=["custom_fra300"],
        active_equipment="custom_fra300",
    )
    profile["equipment_definitions"] = {
        "custom_fra300": {"focal_length_mm": 300}
    }

    with pytest.raises(
        tonight_service_module.TonightEquipmentSelectionError,
        match="invalid_tonight_equipment",
    ):
        resolve_tonight_equipment(profile, None)


def forecast_run(nights):
    return ForecastRun(nights=nights, evidence=FORECAST_EVIDENCE)


class RecordingRecommendationService:
    def __init__(self, recommendation=None):
        self.recommendation = recommendation
        self.calls = []

    def build(self, *, candidates):
        self.calls.append(candidates)
        return self.recommendation


class RecordingMissionService:
    def __init__(self, mission=None):
        self.mission = mission
        self.calls = []

    def create(self, winner, objects, recommended_key, build_mission_input):
        self.calls.append(
            {
                "winner": winner,
                "objects": objects,
                "recommended_key": recommended_key,
                "build_mission_input": build_mission_input,
            }
        )
        return self.mission


def make_candidate(catalog_key="M31"):
    return Candidate(
        name="Andromeda",
        catalog_key=catalog_key,
        priority=1.0,
        astro_score=82.0,
        final_score=79.0,
        decision_score=77.0,
        portfolio_score=75.0,
        global_score=81.0,
        setup_score=68.0,
        best_setup="widefield",
        closure_bonus=0.0,
    )


def make_recommendation(candidate):
    return Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=1.0,
    )


def make_service(
    *,
    forecast_nights,
    build_candidates,
    recommendation=None,
    mission=None,
    build_mission_input=lambda evaluation, *, profile: (evaluation, profile),
):
    recommendation_service = RecordingRecommendationService(recommendation)
    mission_service = RecordingMissionService(mission)
    service = TonightApplicationService(
        forecast_nights=forecast_nights,
        build_candidates=build_candidates,
        opportunity_recommendation_service=recommendation_service,
        tonight_mission_service=mission_service,
        build_mission_input=build_mission_input,
    )
    return service, recommendation_service, mission_service


def test_evaluate_requires_explicit_bortle_keyword():
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([]),
        build_candidates=lambda *args, **kwargs: [],
    )

    with pytest.raises(TypeError, match="bortle"):
        service.evaluate(
            profile={},
            weather=object(),
            reference_time_utc=REFERENCE_TIME,
        )


def test_tonight_inputs_preserve_optional_availability_identity():
    profile = make_profile()
    availability = SessionAvailability(
        SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=2),
    )

    omitted = resolve_tonight_inputs(profile, bortle=4)
    explicit = resolve_tonight_inputs(
        profile,
        bortle=4,
        availability=availability,
    )

    assert omitted.availability is None
    assert explicit.availability is availability


def test_evaluate_carries_typed_availability_to_composition_boundary(monkeypatch):
    availability = SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)
    resolved_availability = []
    original_resolver = tonight_service_module.resolve_tonight_inputs

    def recording_resolver(*args, **kwargs):
        inputs = original_resolver(*args, **kwargs)
        resolved_availability.append(inputs.availability)
        return inputs

    monkeypatch.setattr(
        tonight_service_module,
        "resolve_tonight_inputs",
        recording_resolver,
    )
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([]),
        build_candidates=lambda *args, **kwargs: [],
    )

    service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=4,
        availability=availability,
    )

    assert resolved_availability == [availability]
    assert resolved_availability[0] is availability


def test_evaluate_defers_availability_bound_mission_until_selection():
    availability = SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)
    mission_input = MissionInput(
        window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        astronomical_hours=4.0,
        weather=None,
        moon_penalty=None,
        recommended_hours=3.0,
        expected_gain=1.0,
    )
    candidate = make_candidate()
    service, _, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run(
            [
                {
                    "date": date(2026, 9, 1),
                    "duration": 4.0,
                    "top_objects": [{"catalog_key": "M31"}],
                }
            ]
        ),
        build_candidates=lambda *args, **kwargs: [candidate],
        recommendation=make_recommendation(candidate),
        mission=object(),
        build_mission_input=lambda evaluation, *, profile: mission_input,
    )
    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=4,
        availability=availability,
    )

    assert result.recommendation.opportunity.candidate is candidate
    assert result.mission is None
    assert result.status is TonightStatus.AVAILABLE
    assert mission_service.calls == []


def _productive_assessment():
    return ProductiveWindowAssessment(
        window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        recommended_hours=3.0,
        expected_gain=1.2,
        productivity=SimpleNamespace(
            timeline=(
                SimpleNamespace(
                    start_hour=0.0,
                    end_hour=1.0,
                    productivity_score=0.1,
                ),
                SimpleNamespace(
                    start_hour=1.0,
                    end_hour=3.0,
                    productivity_score=0.9,
                ),
                SimpleNamespace(
                    start_hour=3.0,
                    end_hour=4.0,
                    productivity_score=0.2,
                ),
            )
        ),
    )


@pytest.mark.parametrize(
    ("availability", "expected_start", "expected_end", "expected_hours"),
    [
        (
            SessionAvailability(SessionAvailabilityMode.ALL_NIGHT),
            datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
            datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
            3.0,
        ),
        (
            SessionAvailability(
                SessionAvailabilityMode.DURATION,
                duration=timedelta(hours=2),
            ),
            datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
            datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
            2.0,
        ),
        (
            SessionAvailability(
                SessionAvailabilityMode.START_AND_DURATION,
                start=datetime(2026, 9, 2, 0, tzinfo=timezone.utc),
                duration=timedelta(hours=3),
            ),
            datetime(2026, 9, 2, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
            2.0,
        ),
        (
            SessionAvailability(
                SessionAvailabilityMode.UNTIL,
                end=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
            ),
            datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
            datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
            3.0,
        ),
        (
            SessionAvailability(
                SessionAvailabilityMode.FIXED_WINDOW,
                start=datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc),
                end=datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc),
            ),
            datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc),
            datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc),
            1.0,
        ),
    ],
)
def test_mission_timing_uses_existing_availability_windowing(
    availability,
    expected_start,
    expected_end,
    expected_hours,
):
    timing = mission_assembler_module._mission_timing_for_availability(
        _productive_assessment(),
        availability,
    )

    assert timing[:3] == (expected_start, expected_end, expected_hours)


def test_mission_timing_omitted_availability_preserves_assessment(monkeypatch):
    assessment = _productive_assessment()
    monkeypatch.setattr(
        availability_windowing,
        "select_duration_availability_window",
        lambda *args, **kwargs: pytest.fail("windowing must not be invoked"),
    )

    timing = mission_assembler_module._mission_timing_for_availability(
        assessment,
        None,
    )

    assert timing == (
        assessment.window_start,
        assessment.window_end,
        assessment.recommended_hours,
        assessment.expected_gain,
    )


def test_mission_timing_empty_intersection_returns_none():
    availability = SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=datetime(2026, 9, 2, 3, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, 4, tzinfo=timezone.utc),
    )

    assert (
        mission_assembler_module._mission_timing_for_availability(
            _productive_assessment(),
            availability,
        )
        is None
    )


def test_empty_availability_is_resolved_only_after_user_selection():
    candidate = make_candidate()
    service, _, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run(
            [
                {
                    "date": date(2026, 9, 1),
                    "duration": 4.0,
                    "top_objects": [{"catalog_key": "M31"}],
                }
            ]
        ),
        build_candidates=lambda *args, **kwargs: [candidate],
        recommendation=make_recommendation(candidate),
        mission=None,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=4,
        availability=SessionAvailability(
            SessionAvailabilityMode.FIXED_WINDOW,
            start=datetime(2026, 9, 2, 3, tzinfo=timezone.utc),
            end=datetime(2026, 9, 2, 4, tzinfo=timezone.utc),
        ),
    )

    assert result.mission is None
    assert result.status is TonightStatus.AVAILABLE
    assert mission_service.calls == []


def test_evaluate_delegates_inputs_selects_earliest_and_preserves_identities():
    profile = {
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183", "fra400_2600"],
        "location": {
            "name": "La Chaux-de-Fonds",
            "latitude": 47.1,
            "longitude": 6.8,
        }
    }
    original_available = profile["available_equipment"]
    weather = object()
    later_objects = [{"catalog_key": "M42"}]
    selected_objects = [
        {
            "catalog_key": "M31",
            "global_score": 91.0,
            "decision_score": 87.0,
            "final_score": 84.0,
            "aqi": 12,
            "framing_score": 73.0,
            "setup_score": 68.0,
            "window_score": 89.0,
        }
    ]
    later = {
        "date": date(2026, 9, 2),
        "duration": 5.0,
        "top_objects": later_objects,
    }
    selected = {
        "date": date(2026, 9, 1),
        "duration": 4.25,
        "top_objects": selected_objects,
    }
    forecast_calls = []
    candidate_calls = []
    candidates = [make_candidate()]
    recommendation = make_recommendation(candidates[0])
    mission = NightMission(
        target="Andromeda",
        confidence="HIGH",
        window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        recommended_hours=3.0,
        productivity=NightProductivityResult(
            astronomical_hours=4.0,
            productive_hours=3.0,
            confidence=0.75,
            cloud_loss=0.5,
            moon_loss=0.25,
            altitude_loss=0.0,
            weather_loss=0.25,
            windows=[
                NightWindow(
                    start_hour=0.0,
                    end_hour=3.0,
                    productivity=0.8,
                    altitude=60.0,
                    cloud_cover=10.0,
                    moon_penalty=0.1,
                    seeing=1.5,
                    productive=True,
                    reason="stable",
                )
            ],
        ),
    )

    def forecast(*args, **kwargs):
        forecast_calls.append((args, kwargs))
        return forecast_run([later, selected])

    def build_candidates(objects, available_hours=3.0, *, profile):
        candidate_calls.append((objects, available_hours, profile))
        return candidates

    service, recommendation_service, mission_service = make_service(
        forecast_nights=forecast,
        build_candidates=build_candidates,
        recommendation=recommendation,
        mission=mission,
    )

    result = service.evaluate(
        profile=profile,
        weather=weather,
        reference_time_utc=REFERENCE_TIME,
        equipment="fra400_2600",
        goal="galaxies",
        target="deep_sky",
        bortle=4,
    )

    assert forecast_calls == [
        (
            (47.1, 6.8, "La Chaux-de-Fonds", 4),
            {
                "target": "deep_sky",
                "goal": "galaxies",
                "weather": weather,
                "profile": {
                    **profile,
                    "active_equipment": "fra400_2600",
                    "available_equipment": ["fra400_2600"],
                },
                "reference_time_utc": REFERENCE_TIME,
            },
        )
    ]
    effective_profile = {
        **profile,
        "active_equipment": "fra400_2600",
        "available_equipment": ["fra400_2600"],
    }
    assert candidate_calls == [(selected_objects, 4.25, effective_profile)]
    forecast_profile = forecast_calls[0][1]["profile"]
    assert forecast_profile is not profile
    assert forecast_profile["location"] == profile["location"]
    assert forecast_profile["location"] is not profile["location"]
    assert recommendation_service.calls == [candidates]
    assert mission_service.calls == []
    assert profile["active_equipment"] == "samyang_183"
    assert profile["available_equipment"] is original_available
    assert profile["available_equipment"] == ["samyang_183", "fra400_2600"]
    assert result.night is selected
    assert result.recommendation is recommendation
    assert result.mission is None
    assert result.forecast_evidence is FORECAST_EVIDENCE
    assert selected["top_objects"] is selected_objects
    assert selected_objects[0]["global_score"] == 91.0
    assert selected_objects[0]["decision_score"] == 87.0
    assert selected_objects[0]["final_score"] == 84.0
    assert selected_objects[0]["aqi"] == 12
    assert selected_objects[0]["framing_score"] == 73.0
    assert selected_objects[0]["setup_score"] == 68.0
    assert selected_objects[0]["window_score"] == 89.0


def test_missing_night_duration_stays_unknown_for_candidate_ranking():
    calls = []
    night = {
        "date": date(2026, 9, 1),
        "top_objects": [],
    }
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda objects, available_hours, *, profile: (
            calls.append((objects, available_hours)) or []
        ),
    )

    service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=4,
    )

    assert calls == [([], None)]


def test_missing_location_is_rejected_before_forecast():
    forecast_calls = []
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_calls.append(args),
        build_candidates=lambda *args, **kwargs: None,
    )
    profile = make_profile()
    profile.pop("location")

    with pytest.raises(UserProfileError, match="location"):
        service.evaluate(
            profile=profile,
            weather=None,
            reference_time_utc=REFERENCE_TIME,
            bortle=3,
        )

    assert forecast_calls == []


def test_no_forecast_nights_stops_all_downstream_work():
    candidate_calls = []
    service, recommendation_service, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([]),
        build_candidates=lambda *args, **kwargs: candidate_calls.append(
            (args, kwargs)
        ),
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result == TonightResult(
        None,
        None,
        None,
        status=TonightStatus.NO_NIGHT,
        forecast_evidence=FORECAST_EVIDENCE,
    )
    assert candidate_calls == []
    assert recommendation_service.calls == []
    assert mission_service.calls == []


def test_unavailable_forecast_is_distinct_from_empty_forecast():
    service, recommendation_service, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: None,
        build_candidates=lambda *args, **kwargs: None,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result == TonightResult(
        None,
        None,
        None,
        status=TonightStatus.FORECAST_UNAVAILABLE,
    )
    assert recommendation_service.calls == []
    assert mission_service.calls == []


def test_no_candidates_preserves_night_and_skips_downstream_services():
    night = {"date": "2026-09-01", "top_objects": []}
    service, recommendation_service, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: [],
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result == TonightResult(
        night,
        None,
        None,
        status=TonightStatus.NO_CANDIDATE,
        forecast_evidence=FORECAST_EVIDENCE,
    )
    assert result.night is night
    assert recommendation_service.calls == []
    assert mission_service.calls == []


def test_candidate_build_result_separates_admitted_candidates_and_rejections():
    night = {"date": "2026-09-01", "top_objects": []}
    candidates = [make_candidate(), make_candidate()]
    rejection = CandidateRejection(
        target="Orion",
        catalog_key="M42",
        provenance=CandidateProvenance.DISCOVERY,
        basis=CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE,
        evaluation_score=0,
    )
    recommendation = make_recommendation(candidates[0])
    service, recommendation_service, _ = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: CandidateBuildResult(
            candidates=tuple(candidates),
            rejections=(rejection,),
        ),
        recommendation=recommendation,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert recommendation_service.calls == [candidates]
    assert result.candidate_rejections == (rejection,)


def test_no_recommendation_preserves_night_and_skips_mission():
    night = {"date": "2026-09-01", "top_objects": []}
    candidates = [make_candidate()]
    service, recommendation_service, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: candidates,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result == TonightResult(
        night,
        None,
        None,
        status=TonightStatus.NO_RECOMMENDATION,
        forecast_evidence=FORECAST_EVIDENCE,
    )
    assert recommendation_service.calls == [candidates]
    assert mission_service.calls == []


def test_recommendation_result_defers_mission_creation():
    night = {"date": "2026-09-01", "top_objects": []}
    candidate = make_candidate()
    candidates = [candidate]
    recommendation = make_recommendation(candidate)
    service, _, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: candidates,
        recommendation=recommendation,
        mission=None,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result.night is night
    assert result.recommendation is recommendation
    assert result.mission is None
    assert result.status is TonightStatus.AVAILABLE
    assert result.forecast_evidence is FORECAST_EVIDENCE
    assert mission_service.calls == []


def test_recommendation_does_not_create_a_mission_before_user_selection():
    night = {"date": "2026-09-01", "top_objects": []}
    candidate = make_candidate()
    recommendation = make_recommendation(candidate)
    provenance_free_mission = NightMission(
        target="M31",
        confidence=0.9,
    )
    service, _, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: [candidate],
        recommendation=recommendation,
        mission=provenance_free_mission,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result.status is TonightStatus.AVAILABLE
    assert result.recommendation is recommendation
    assert result.mission is None
    assert mission_service.calls == []


def test_productivity_mission_status_is_deferred_until_selection():
    night = {"date": "2026-09-01", "top_objects": []}
    candidate = make_candidate()
    recommendation = make_recommendation(candidate)
    mission = NightMission(
        target="Andromeda",
        confidence=0.9,
        window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
        recommended_hours=0.0,
        productivity=NightProductivityResult(
            astronomical_hours=3.0,
            productive_hours=0.9,
            confidence=0.3,
            cloud_loss=1.5,
            moon_loss=0.4,
            altitude_loss=0.0,
            weather_loss=0.2,
            windows=[],
        ),
    )
    service, _, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: [candidate],
        recommendation=recommendation,
        mission=mission,
    )

    result = service.evaluate(
        profile=make_profile(),
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        bortle=3,
    )

    assert result.status is TonightStatus.AVAILABLE
    assert result.mission is None
    assert result.forecast_evidence is FORECAST_EVIDENCE
    assert mission_service.calls == []


@pytest.mark.parametrize(
    "available_equipment",
    [
        ["samyang_183"],
        ["samyang_183", "fra400_2600"],
    ],
)
def test_active_equipment_is_the_only_setup_exposed_to_tonight_forecast(
    available_equipment,
):
    calls = []
    profile = make_profile(available_equipment=available_equipment)
    original_available = profile["available_equipment"]
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: (
            calls.append(kwargs) or forecast_run([])
        ),
        build_candidates=lambda *args, **kwargs: [],
    )

    service.evaluate(
        profile=profile,
        weather=object(),
        reference_time_utc=REFERENCE_TIME,
        equipment=None,
        bortle=3,
    )

    assert calls[0]["profile"]["active_equipment"] == "samyang_183"
    assert calls[0]["profile"]["available_equipment"] == ["samyang_183"]
    assert "equipment" not in calls[0]
    assert profile["available_equipment"] is original_available
    assert profile["available_equipment"] == available_equipment


@pytest.mark.parametrize("requested_equipment", ["fra400_2600", "not_a_setup"])
def test_unavailable_or_unknown_override_is_rejected_before_forecast(
    requested_equipment,
):
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: pytest.fail(
            "forecast must not run for invalid equipment"
        ),
        build_candidates=lambda *args, **kwargs: [],
    )

    with pytest.raises(
        tonight_service_module.TonightEquipmentSelectionError,
        match="invalid_tonight_equipment",
    ):
        service.evaluate(
            profile=make_profile(),
            weather=object(),
            reference_time_utc=REFERENCE_TIME,
            equipment=requested_equipment,
            bortle=3,
        )
