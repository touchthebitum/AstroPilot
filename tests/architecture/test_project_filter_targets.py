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

def test_filter_targets_are_consistent_with_project_target():
    project = {
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 4.0,
        },
    }

    assert ProjectFilterTargets.is_consistent(project)


def test_filter_targets_detect_inconsistent_project_target():
    project = {
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 2.0,
        },
    }

    assert not ProjectFilterTargets.is_consistent(project)


def test_filter_targets_validation_rejects_inconsistent_total():
    project = {
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 2.0,
        },
    }

    try:
        ProjectFilterTargets.validate(project)
    except ValueError as exc:
        assert "must match target_hours" in str(exc)
    else:
        raise AssertionError(
            "Expected inconsistent filter targets "
            "to raise ValueError"
        )
