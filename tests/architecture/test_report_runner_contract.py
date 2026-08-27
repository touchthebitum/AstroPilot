from types import SimpleNamespace

from decision.runners.report_runner import ReportRunner


class RecordingForecastEngine:
    def __init__(self, roadmap):
        self.roadmap = roadmap
        self.calls = []

    def simulate_dynamic_portfolio_roadmap(self, *, night_capacities):
        self.calls.append(night_capacities)
        return self.roadmap


class RecordingMissionService:
    def __init__(self, mission=None):
        self.mission = mission
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.mission


def make_runner(*, roadmap=None, mission=None):
    roadmap = roadmap if roadmap is not None else []
    forecast_engine = RecordingForecastEngine(roadmap)
    mission_service = RecordingMissionService(mission)
    calendar_calls = []
    completion_calls = []
    presented_missions = []

    runner = ReportRunner(
        portfolio_forecast_engine=forecast_engine,
        show_multi_night_portfolio_roadmap=(
            lambda value: calendar_calls.append(value)
        ),
        show_portfolio_completion_forecast=(
            lambda value, **kwargs: completion_calls.append(
                (value, kwargs)
            )
        ),
        present_mission=presented_missions.append,
        tonight_mission_service=mission_service,
    )

    return SimpleNamespace(
        runner=runner,
        forecast_engine=forecast_engine,
        mission_service=mission_service,
        calendar_calls=calendar_calls,
        completion_calls=completion_calls,
        presented_missions=presented_missions,
    )


def test_portfolio_mode_passes_roadmap_and_completion_options():
    roadmap = [SimpleNamespace(project="M31")]
    capacities = [{"hours": 3}]
    context = make_runner(roadmap=roadmap)

    context.runner.run_portfolio(
        capacities,
        title="Prévision",
        compact=True,
    )

    assert context.forecast_engine.calls == [capacities]
    assert context.completion_calls == [
        (roadmap, {"title": "Prévision", "compact": True})
    ]
    assert context.calendar_calls == []


def test_calendar_mode_returns_the_presented_roadmap():
    roadmap = [SimpleNamespace(project="M42")]
    context = make_runner(roadmap=roadmap)

    result = context.runner.run_calendar([{"hours": 2}])

    assert result is roadmap
    assert context.calendar_calls == [roadmap]
    assert context.completion_calls == []


def test_full_mode_reuses_one_simulation_for_both_presenters():
    roadmap = [SimpleNamespace(project="M31")]
    capacities = [{"hours": 4}]
    context = make_runner(roadmap=roadmap)

    context.runner.run_full(capacities, detailed=True)

    assert context.forecast_engine.calls == [capacities]
    assert context.calendar_calls == [roadmap]
    assert context.completion_calls == [
        (roadmap, {"detailed": True})
    ]


def test_tonight_mode_uses_candidate_catalog_key_to_create_mission():
    mission = SimpleNamespace(target="M31")
    winner = {"date": "2026-08-27"}
    objects = [{"catalog_key": "M31"}]
    build_mission_input = object()
    recommendation = SimpleNamespace(
        opportunity=SimpleNamespace(
            candidate={"catalog_key": "M31", "name": "Andromeda"}
        )
    )
    context = make_runner(mission=mission)

    context.runner.run_tonight(
        top_nights=[winner],
        winner=winner,
        objects=objects,
        recommendation=recommendation,
        build_mission_input=build_mission_input,
    )

    assert context.mission_service.calls == [
        {
            "winner": winner,
            "objects": objects,
            "recommended_key": "M31",
            "build_mission_input": build_mission_input,
        }
    ]
    assert context.presented_missions == [mission]


def test_tonight_mode_falls_back_to_candidate_name():
    recommendation = SimpleNamespace(
        opportunity=SimpleNamespace(candidate={"name": "M42"})
    )
    context = make_runner()

    context.runner.run_tonight(
        top_nights=[],
        winner={},
        objects=[],
        recommendation=recommendation,
        build_mission_input=object(),
    )

    assert context.mission_service.calls[0]["recommended_key"] == "M42"


def test_tonight_mode_does_not_present_missing_mission():
    context = make_runner(mission=None)

    context.runner.run_tonight(
        top_nights=[],
        winner={},
        objects=[],
        recommendation=None,
        build_mission_input=object(),
    )

    assert context.mission_service.calls == []
    assert context.presented_missions == []
