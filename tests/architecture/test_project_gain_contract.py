import decision.portfolio.project_gain as project_gain


def project_snapshot(
    *,
    hours,
    target_hours,
):
    return {
        "M31": {
            "hours": hours,
            "target_hours": target_hours,
        }
    }

def test_marginal_gain_factor_rewards_early_progress():
    assert project_gain.marginal_gain_factor(0) == 1.4
    assert project_gain.marginal_gain_factor(50) == 1.0
    assert project_gain.marginal_gain_factor(95) == 0.5


def test_portfolio_gain_if_shot_uses_project_state():
    projects = project_snapshot(
        hours=0,
        target_hours=20,
    )

    gain = project_gain.portfolio_gain_if_shot(
        "M31",
        session_hours=2,
        projects=projects,
    )

    assert gain == 14.0


def test_session_portfolio_gain_uses_remaining_hours():
    projects = project_snapshot(
        hours=18,
        target_hours=20,
    )

    gain = project_gain.session_portfolio_gain(
        "M31",
        session_hours=3,
        projects=projects,
    )

    assert gain == 10.0

def test_session_roi_measures_project_gain_per_hour():
    projects = project_snapshot(
        hours=0,
        target_hours=20,
    )

    roi = project_gain.session_roi(
        "M31",
        session_hours=2,
        projects=projects,
    )

    assert roi == 5.0
