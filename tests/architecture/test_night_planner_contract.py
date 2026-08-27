from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from decision.mission.night_planner import NightPlanner, NightTask


def test_night_planner_only_builds_operational_tasks():
    productivity = SimpleNamespace(
        windows=[
            SimpleNamespace(
                productive=True,
                start_hour=1.0,
                end_hour=3.0,
                productivity=0.9,
            ),
        ],
    )

    tasks = NightPlanner.build(productivity)

    assert [task.title for task in tasks] == [
        "Installer le matériel",
        "Mise en station",
        "Autofocus",
        "Flats",
    ]

    assert all(
        task.title != "Acquisition"
        for task in tasks
    )


def test_night_planner_preserves_the_operational_sequence_and_timings():
    tasks = NightPlanner.build(None)

    assert tasks == [
        NightTask("T-30 min", "T-20 min", "Installer le matériel"),
        NightTask("T-20 min", "T-10 min", "Mise en station"),
        NightTask("T-10 min", "T", "Autofocus"),
        NightTask("Fin", "Fin +10 min", "Flats"),
    ]


def test_night_planner_does_not_mutate_productivity_input():
    window = SimpleNamespace(
        productive=True,
        start_hour=1.0,
        end_hour=3.0,
        productivity=0.9,
    )
    productivity = SimpleNamespace(windows=[window])
    original_windows = list(productivity.windows)
    original_values = vars(window).copy()

    NightPlanner.build(productivity)

    assert productivity.windows == original_windows
    assert vars(window) == original_values


def test_night_planner_returns_an_independent_task_list_each_time():
    first = NightPlanner.build(None)
    second = NightPlanner.build(None)

    first.pop()

    assert len(first) == 3
    assert len(second) == 4


def test_night_tasks_are_immutable_value_objects():
    task = NightPlanner.build(None)[0]

    with pytest.raises(FrozenInstanceError):
        task.title = "Changed"


def test_night_task_defaults_are_stable():
    task = NightTask("start", "end", "title")

    assert task.description == ""
    assert task.priority == 0
    assert task.productivity == 0.0
