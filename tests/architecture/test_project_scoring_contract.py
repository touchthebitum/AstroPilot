import decision.portfolio.project_scoring as project_scoring


def project_snapshot(*, hours, target_hours, importance=5):
    return {
        "M31": {
            "hours": hours,
            "target_hours": target_hours,
            "importance": importance,
        }
    }

def test_closure_bonus_rewards_finishable_project():
    projects = project_snapshot(
        hours=18,
        target_hours=20,
    )

    assert project_scoring.closure_bonus(
        "M31",
        available_hours=2,
        projects=projects,
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

    assert score == 48.0


def test_project_priority_normalizes_importance_to_100_scale():
    projects = project_snapshot(
        hours=3,
        target_hours=20,
        importance=8,
    )

    assert project_scoring.project_priority("M31", projects) == 80.0

def test_closure_bonus_for_remaining_uses_session_capacity():
    assert (
        project_scoring.closure_bonus_for_remaining(
            6,
            available_hours=6,
        )
        == 15
    )

    assert (
        project_scoring.closure_bonus_for_remaining(
            10,
            available_hours=3,
        )
        == 0
    )
