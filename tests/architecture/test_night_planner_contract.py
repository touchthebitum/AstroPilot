from types import SimpleNamespace

from decision.mission.night_planner import NightPlanner


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