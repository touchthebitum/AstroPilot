from decision.portfolio.project_filter_targets import (
    ProjectFilterTargets,
)


def test_project_filter_targets_preserve_configured_hours():
    project = {
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 4.0,
        },
    }

    targets = ProjectFilterTargets.get(project)

    assert targets == {
        "Ha": 6.0,
        "OIII": 5.0,
        "SII": 4.0,
    }

    assert (
        ProjectFilterTargets.total_target_hours(project)
        == 15.0
    )


def test_project_without_filter_targets_remains_valid():
    project = {
        "target_hours": 20.0,
    }

    assert ProjectFilterTargets.get(project) == {}
    assert (
        ProjectFilterTargets.total_target_hours(project)
        == 0.0
    )


def test_negative_filter_target_is_clamped_to_zero():
    project = {
        "filter_targets": {
            "Ha": -2.0,
        },
    }

    assert ProjectFilterTargets.get(project) == {
        "Ha": 0.0,
    }