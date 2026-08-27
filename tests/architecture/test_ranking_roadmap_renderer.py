from decision.renderer.recommendation_renderer import (
    render_after_tonight_roadmap,
    render_decision_analysis,
    render_top_projects,
    render_top_roi,
)


def test_after_tonight_roadmap_limits_details_but_totals_all_projects(capsys):
    roadmap = [
        {
            "name": f"Project {index}",
            "remaining": float(index),
            "roi": index / 10,
            "session_gain": float(index * 2),
            "estimated_nights": index / 2,
        }
        for index in range(1, 5)
    ]

    render_after_tonight_roadmap(
        roadmap,
        night_projects=[{"name": "unused"}],
    )

    output = capsys.readouterr().out

    assert "===== ROADMAP APRÈS CETTE NUIT =====" in output
    assert "1. Project 1" in output
    assert "2. Project 2" in output
    assert "3. Project 3" in output
    assert "Project 4" not in output
    assert "Temps total restant : 10.0 h" in output
    assert "Nuits restantes estimées : 5.0" in output


def test_top_projects_limits_output_and_calls_gain_functions_for_top_three(
    capsys,
):
    projects = [
        {"name": f"P{index}", "final_score": 100 - index}
        for index in range(1, 5)
    ]
    portfolio_calls = []
    session_calls = []

    def portfolio_gain(name, *, session_hours):
        portfolio_calls.append((name, session_hours))
        return {"P1": 6.0, "P2": 4.0, "P3": 2.0}[name]

    def session_gain(name, session_hours):
        session_calls.append((name, session_hours))
        return {"P1": 5.0, "P2": 3.0, "P3": 1.0}[name]

    render_top_projects(
        night_projects=projects,
        session_hours=2.0,
        portfolio_gain_if_shot=portfolio_gain,
        session_portfolio_gain=session_gain,
    )

    output = capsys.readouterr().out

    assert "===== TOP PROJETS CE SOIR =====" in output
    assert "1. P1 (score 99.0) gain +6.0% ROI 3.00/h" in output
    assert "2. P2 (score 98.0) gain +4.0% ROI 2.00/h" in output
    assert "3. P3 (score 97.0) gain +2.0% ROI 1.00/h" in output
    assert "P4" not in output
    assert portfolio_calls == [("P1", 2.0), ("P2", 2.0), ("P3", 2.0)]
    assert session_calls == [("P1", 2.0), ("P2", 2.0), ("P3", 2.0)]


def test_top_projects_uses_zero_roi_for_zero_session_duration(capsys):
    render_top_projects(
        night_projects=[{"name": "M31", "final_score": 90.0}],
        session_hours=0.0,
        portfolio_gain_if_shot=lambda name, *, session_hours: 5.0,
        session_portfolio_gain=lambda name, session_hours: 4.0,
    )

    assert "ROI 0.00/h" in capsys.readouterr().out


def test_top_roi_sorts_by_computed_roi_without_mutating_projects(capsys):
    projects = [{"name": f"P{index}"} for index in range(1, 7)]
    original_names = [project["name"] for project in projects]
    gains = {
        "P1": 2.0,
        "P2": 12.0,
        "P3": 4.0,
        "P4": 10.0,
        "P5": 6.0,
        "P6": 8.0,
    }
    calls = []

    def portfolio_gain(name, *, session_hours):
        calls.append((name, session_hours))
        return gains[name]

    render_top_roi(
        night_projects=projects,
        session_hours=2.0,
        portfolio_gain_if_shot=portfolio_gain,
    )

    output = capsys.readouterr().out

    assert "1. P2 ROI 6.00/h (gain +12.0%)" in output
    assert "2. P4 ROI 5.00/h (gain +10.0%)" in output
    assert "3. P6 ROI 4.00/h (gain +8.0%)" in output
    assert "4. P5 ROI 3.00/h (gain +6.0%)" in output
    assert "5. P3 ROI 2.00/h (gain +4.0%)" in output
    assert "P1 ROI" not in output
    assert calls == [(name, 2.0) for name in original_names]
    assert [project["name"] for project in projects] == original_names


def test_decision_analysis_reports_converging_score_and_roi(capsys):
    render_decision_analysis(
        best_score={"name": "M31"},
        best_roi={"name": "M31"},
    )

    output = capsys.readouterr().out

    assert "===== ANALYSE DECISION =====" in output
    assert (
        "✓ M31 est à la fois le meilleur score astro et le meilleur ROI."
        in output
    )


def test_decision_analysis_does_not_claim_convergence_for_distinct_choices(
    capsys,
):
    render_decision_analysis(
        best_score={"name": "M31"},
        best_roi={"name": "M42"},
    )

    output = capsys.readouterr().out

    assert "===== ANALYSE DECISION =====" in output
    assert "à la fois" not in output
