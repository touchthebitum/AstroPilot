import decision.portfolio.project_state as project_state_module

from decision.portfolio.project_state import project_state


def test_project_state_returns_canonical_progress(monkeypatch):
    monkeypatch.setattr(
        project_state_module,
        "get_projects",
        lambda: {
            "M31": {
                "hours": 3.0,
                "target_hours": 20.0,
                "importance": 8,
            }
        },
    )

    state = project_state("M31")

    assert state == {
        "hours": 3.0,
        "target_hours": 20.0,
        "remaining": 17.0,
        "progress": 15.0,
    }


def test_project_state_returns_none_for_unknown_project(monkeypatch):
    monkeypatch.setattr(
        project_state_module,
        "get_projects",
        lambda: {},
    )

    assert project_state("UNKNOWN") is None


def test_project_state_handles_zero_target(monkeypatch):
    monkeypatch.setattr(
        project_state_module,
        "get_projects",
        lambda: {
            "M31": {
                "hours": 3.0,
                "target_hours": 0.0,
            }
        },
    )

    state = project_state("M31")

    assert state == {
        "hours": 3.0,
        "target_hours": 0.0,
        "remaining": 0.0,
        "progress": 0.0,
    }