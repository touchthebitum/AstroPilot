from decision.portfolio.project_state import (
    project_state,
    project_state_from_project,
)


def test_project_state_from_project_is_independent_of_storage():
    assert project_state_from_project(
        {
            "hours": 3.0,
            "target_hours": 20.0,
        }
    ) == {
        "hours": 3.0,
        "target_hours": 20.0,
        "remaining": 17.0,
        "progress": 15.0,
    }


def test_project_state_from_project_accepts_missing_project():
    assert project_state_from_project(None) is None


def test_project_state_returns_canonical_progress():
    projects = {
            "M31": {
                "hours": 3.0,
                "target_hours": 20.0,
                "importance": 8,
            }
        }

    state = project_state("M31", projects)

    assert state == {
        "hours": 3.0,
        "target_hours": 20.0,
        "remaining": 17.0,
        "progress": 15.0,
    }


def test_project_state_returns_none_for_unknown_project():
    assert project_state("UNKNOWN", {}) is None


def test_project_state_handles_zero_target():
    projects = {
            "M31": {
                "hours": 3.0,
                "target_hours": 0.0,
            }
        }

    state = project_state("M31", projects)

    assert state == {
        "hours": 3.0,
        "target_hours": 0.0,
        "remaining": 0.0,
        "progress": 0.0,
    }
