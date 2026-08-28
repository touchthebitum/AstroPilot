import copy

import pytest

from decision.models.future_opportunity import FutureOpportunity
from decision.portfolio.portfolio_forecast_engine import (
    PortfolioForecastEngine,
)


class StableFutureEngine:
    def estimate(self, project_name, **kwargs):
        return FutureOpportunity(
            good_nights=10,
            risk="FAIBLE",
            weather_ratio=1.0,
            needed_nights=1,
            opportunity_ratio=10.0,
        )


def simulate(monkeypatch, projects, night_capacities):
    engine = PortfolioForecastEngine(
        future_engine=StableFutureEngine(),
        score_project=lambda project, available_hours: project.get(
            "priority",
            0,
        ),
        project_provider=lambda: projects,
    )

    return engine.simulate_dynamic_portfolio_roadmap(
        night_capacities=night_capacities,
    )


def test_simulation_never_exceeds_a_project_target(monkeypatch):
    roadmap = simulate(
        monkeypatch,
        projects={
            "M31": {
                "hours": 1.5,
                "target_hours": 3,
            }
        },
        night_capacities=[{"hours": 8}],
    )

    assert sum(step["hours"] for step in roadmap) == pytest.approx(1.5)
    assert all(
        step["current_hours"] <= step["target_hours"]
        for step in roadmap
    )
    assert roadmap[-1]["remaining_after"] == 0


def test_simulation_never_uses_more_than_each_night_capacity(
    monkeypatch,
):
    capacities = [
        {"date": "2026-08-27", "hours": 2.5},
        {"date": "2026-08-28", "hours": 1.25},
    ]
    roadmap = simulate(
        monkeypatch,
        projects={
            "M31": {
                "hours": 0,
                "target_hours": 10,
            }
        },
        night_capacities=capacities,
    )

    for night, capacity in enumerate(capacities, start=1):
        used = sum(
            step["hours"]
            for step in roadmap
            if step["night"] == night
        )
        assert used <= capacity["hours"]


def test_simulation_does_not_mutate_source_portfolio(monkeypatch):
    projects = {
        "M31": {
            "hours": 1,
            "target_hours": 4,
            "priority": 2,
        },
        "M42": {
            "hours": 0.5,
            "target_hours": 3,
            "priority": 1,
        },
    }
    original = copy.deepcopy(projects)

    simulate(
        monkeypatch,
        projects=projects,
        night_capacities=[{"hours": 4}],
    )

    assert projects == original


def test_simulated_hours_and_remaining_hours_stay_balanced(
    monkeypatch,
):
    initial_hours = {"M31": 1.0, "M42": 0.5}
    roadmap = simulate(
        monkeypatch,
        projects={
            "M31": {
                "hours": initial_hours["M31"],
                "target_hours": 4,
                "priority": 2,
            },
            "M42": {
                "hours": initial_hours["M42"],
                "target_hours": 3,
                "priority": 1,
            },
        },
        night_capacities=[{"hours": 2}, {"hours": 2}],
    )

    assert sum(step["hours"] for step in roadmap) == pytest.approx(4)

    for project_name, starting_hours in initial_hours.items():
        project_steps = [
            step
            for step in roadmap
            if step["project"] == project_name
        ]
        simulated_hours = sum(step["hours"] for step in project_steps)

        if project_steps:
            last_step = project_steps[-1]
            assert last_step["current_hours"] == pytest.approx(
                starting_hours + simulated_hours
            )
            assert (
                last_step["current_hours"]
                + last_step["remaining_after"]
            ) == pytest.approx(last_step["target_hours"])


def test_project_completes_when_remainder_is_smaller_than_capacity(
    monkeypatch,
):
    roadmap = simulate(
        monkeypatch,
        projects={
            "M31": {
                "hours": 4.25,
                "target_hours": 5,
            }
        },
        night_capacities=[{"hours": 3}],
    )

    assert roadmap == [
        {
            "night": 1,
            "date": None,
            "capacity": 3,
            "project": "M31",
            "score": 3.0,
            "hours": 0.75,
            "target_hours": 5,
            "current_hours": 5.0,
            "remaining_after": 0,
            "completed": True,
        }
    ]
