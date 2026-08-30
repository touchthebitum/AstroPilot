from datetime import date, datetime, timezone

from decision.forecast.forecast_run import ForecastRun
from decision.mission.night_mission import NightMission
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
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


FORECAST_EVIDENCE = DecisionForecastEvidence(())
REFERENCE_TIME = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)


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


def test_evaluate_delegates_inputs_selects_earliest_and_preserves_identities():
    profile = {
        "location": {
            "name": "La Chaux-de-Fonds",
            "latitude": 47.1,
            "longitude": 6.8,
        }
    }
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
        equipment="portable",
        goal="galaxies",
        target="deep_sky",
        bortle=4,
    )

    assert forecast_calls == [
        (
            (47.1, 6.8, "La Chaux-de-Fonds", 4),
            {
                "target": "deep_sky",
                "equipment": "portable",
                "goal": "galaxies",
                "weather": weather,
                "profile": profile,
                "reference_time_utc": REFERENCE_TIME,
            },
        )
    ]
    assert candidate_calls == [(selected_objects, 4.25, profile)]
    assert recommendation_service.calls == [candidates]
    assert mission_service.calls[0]["winner"] is selected
    assert mission_service.calls[0]["objects"] is selected_objects
    assert mission_service.calls[0]["recommended_key"] == "M31"
    evaluation = object()
    assert mission_service.calls[0]["build_mission_input"](evaluation) == (
        evaluation,
        profile,
    )
    assert result.night is selected
    assert result.recommendation is recommendation
    assert result.mission is mission
    assert result.forecast_evidence is FORECAST_EVIDENCE
    assert selected["top_objects"] is selected_objects
    assert selected_objects[0]["global_score"] == 91.0
    assert selected_objects[0]["decision_score"] == 87.0
    assert selected_objects[0]["final_score"] == 84.0
    assert selected_objects[0]["aqi"] == 12
    assert selected_objects[0]["framing_score"] == 73.0
    assert selected_objects[0]["setup_score"] == 68.0
    assert selected_objects[0]["window_score"] == 89.0


def test_location_defaults_match_current_cli_policy():
    calls = []

    def forecast(*args, **kwargs):
        calls.append((args, kwargs))
        return forecast_run([])

    service, _, _ = make_service(
        forecast_nights=forecast,
        build_candidates=lambda *args, **kwargs: None,
    )
    profile = {}
    weather = object()

    result = service.evaluate(
        profile=profile,
        weather=weather,
        reference_time_utc=REFERENCE_TIME,
    )

    assert calls == [
        (
            (46.7508, 6.5495, "Buttes", 3),
            {
                "target": "deep_sky",
                "equipment": None,
                "goal": "balanced",
                "weather": weather,
                "profile": profile,
                "reference_time_utc": REFERENCE_TIME,
            },
        )
    ]
    assert result == TonightResult(
        None,
        None,
        None,
        status=TonightStatus.NO_NIGHT,
        forecast_evidence=FORECAST_EVIDENCE,
    )


def test_no_forecast_nights_stops_all_downstream_work():
    candidate_calls = []
    service, recommendation_service, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([]),
        build_candidates=lambda *args, **kwargs: candidate_calls.append(
            (args, kwargs)
        ),
    )

    result = service.evaluate(
        profile={}, weather=object(), reference_time_utc=REFERENCE_TIME
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
        profile={}, weather=object(), reference_time_utc=REFERENCE_TIME
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
        profile={}, weather=object(), reference_time_utc=REFERENCE_TIME
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


def test_no_recommendation_preserves_night_and_skips_mission():
    night = {"date": "2026-09-01", "top_objects": []}
    candidates = [make_candidate()]
    service, recommendation_service, mission_service = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: candidates,
    )

    result = service.evaluate(
        profile={}, weather=object(), reference_time_utc=REFERENCE_TIME
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


def test_missing_mission_preserves_exact_night_and_recommendation():
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
        profile={}, weather=object(), reference_time_utc=REFERENCE_TIME
    )

    assert result.night is night
    assert result.recommendation is recommendation
    assert result.mission is None
    assert result.status is TonightStatus.NO_MISSION
    assert result.forecast_evidence is FORECAST_EVIDENCE
    assert len(mission_service.calls) == 1


def test_night_without_a_productive_window_is_not_available():
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
    service, _, _ = make_service(
        forecast_nights=lambda *args, **kwargs: forecast_run([night]),
        build_candidates=lambda *args, **kwargs: [candidate],
        recommendation=recommendation,
        mission=mission,
    )

    result = service.evaluate(
        profile={}, weather=object(), reference_time_utc=REFERENCE_TIME
    )

    assert result.status is TonightStatus.NO_PRODUCTIVE_WINDOW
    assert result.mission is mission
    assert result.forecast_evidence is FORECAST_EVIDENCE
