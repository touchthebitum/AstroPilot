from types import SimpleNamespace

from decision.runners.tonight_runner import TonightRunner


class RecordingReportRunner:
    def __init__(self):
        self.mission_calls = []
        self.forecasts = []

    def run_tonight(self, **kwargs):
        self.mission_calls.append(kwargs)

    def show_portfolio_completion_forecast(self, roadmap):
        self.forecasts.append(roadmap)


class RecordingForecastEngine:
    def __init__(self, roadmap=None):
        self.roadmap = roadmap or []
        self.capacities = []

    def simulate_dynamic_portfolio_roadmap(self, *, night_capacities):
        self.capacities.append(night_capacities)
        return self.roadmap


class RecordingRecommendationService:
    def __init__(self, recommendation=None):
        self.recommendation = recommendation
        self.candidate_calls = []

    def build(self, *, candidates):
        self.candidate_calls.append(candidates)
        return self.recommendation


def make_runner(
    *,
    recommend_project_for_night,
    recommendation=None,
    roadmap=None,
):
    report_runner = RecordingReportRunner()
    forecast_engine = RecordingForecastEngine(roadmap=roadmap)
    recommendation_service = RecordingRecommendationService(
        recommendation=recommendation,
    )
    build_mission_input = object()

    runner = TonightRunner(
        report_runner=report_runner,
        portfolio_forecast_engine=forecast_engine,
        build_mission_input=build_mission_input,
        recommend_project_for_night=recommend_project_for_night,
        opportunity_recommendation_service=recommendation_service,
    )

    return SimpleNamespace(
        runner=runner,
        report_runner=report_runner,
        forecast_engine=forecast_engine,
        recommendation_service=recommendation_service,
        build_mission_input=build_mission_input,
    )


def test_empty_night_list_stops_all_work():
    recommendation_calls = []
    context = make_runner(
        recommend_project_for_night=lambda *args, **kwargs: (
            recommendation_calls.append((args, kwargs))
        ),
    )

    context.runner.run(top_nights=[], night_capacities=[{"hours": 3}])

    assert recommendation_calls == []
    assert context.report_runner.mission_calls == []
    assert context.forecast_engine.capacities == []


def test_winner_duration_and_objects_are_passed_to_project_selection():
    captured = {}
    top_objects = [SimpleNamespace(name="M31")]

    def recommend(objects, *, available_hours):
        captured["objects"] = objects
        captured["available_hours"] = available_hours
        return []

    context = make_runner(recommend_project_for_night=recommend)

    context.runner.run(
        top_nights=[{"duration": 4.5, "top_objects": top_objects}],
        night_capacities=[],
    )

    assert captured["objects"] is top_objects
    assert captured["available_hours"] == 4.5


def test_missing_duration_defaults_to_three_hours():
    captured = {}

    def recommend(objects, *, available_hours):
        captured["available_hours"] = available_hours
        return []

    context = make_runner(recommend_project_for_night=recommend)

    context.runner.run(top_nights=[{}], night_capacities=[])

    assert captured["available_hours"] == 3.0


def test_missing_recommendation_skips_mission_but_keeps_forecast():
    candidates = [SimpleNamespace(name="M31")]
    roadmap = [SimpleNamespace(project="M31")]
    capacities = [{"hours": 3}]
    context = make_runner(
        recommend_project_for_night=lambda *args, **kwargs: candidates,
        recommendation=None,
        roadmap=roadmap,
    )

    context.runner.run(
        top_nights=[{"top_objects": []}],
        night_capacities=capacities,
    )

    assert context.recommendation_service.candidate_calls == [candidates]
    assert context.report_runner.mission_calls == []
    assert context.forecast_engine.capacities == [capacities]
    assert context.report_runner.forecasts == [roadmap]


def test_recommendation_runs_mission_with_original_context():
    winner = {"duration": 2, "top_objects": ["M31"]}
    top_nights = [winner, {"top_objects": ["M42"]}]
    candidates = [SimpleNamespace(name="M31")]
    recommendation = SimpleNamespace(opportunity="M31")
    context = make_runner(
        recommend_project_for_night=lambda *args, **kwargs: candidates,
        recommendation=recommendation,
    )

    context.runner.run(top_nights=top_nights, night_capacities=[])

    assert context.report_runner.mission_calls == [
        {
            "winner": winner,
            "objects": winner["top_objects"],
            "recommendation": recommendation,
            "build_mission_input": context.build_mission_input,
            "top_nights": top_nights,
        }
    ]
