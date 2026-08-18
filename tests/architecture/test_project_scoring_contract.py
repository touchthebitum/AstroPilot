import decision.portfolio.project_scoring as project_scoring
import decision.portfolio.project_state as project_state_module


def install_project(monkeypatch, *, hours, target_hours, importance=5):
    projects = {
        "M31": {
            "hours": hours,
            "target_hours": target_hours,
            "importance": importance,
        }
    }

    monkeypatch.setattr(
        project_scoring,
        "get_projects",
        lambda: projects,
    )
    monkeypatch.setattr(
        project_state_module,
        "get_projects",
        lambda: projects,
    )


def test_project_roi_uses_current_project_state(monkeypatch):
    install_project(
        monkeypatch,
        hours=10,
        target_hours=20,
        importance=8,
    )

    assert project_scoring.project_roi("M31") == 1.2


def test_closure_bonus_rewards_finishable_project(monkeypatch):
    install_project(
        monkeypatch,
        hours=18,
        target_hours=20,
    )

    assert project_scoring.closure_bonus(
        "M31",
        available_hours=2,
    ) == 15


def test_simulated_portfolio_score_uses_virtual_project_state():
    project = {
        "hours": 10,
        "target_hours": 20,
        "importance": 8,
    }

    score = project_scoring.simulated_portfolio_score(
        project
    )

    assert score == 117.0
