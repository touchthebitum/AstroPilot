import decision.portfolio.portfolio_presenter as module


def test_incomplete_portfolio_reports_completion_beyond_horizon(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        module,
        "get_projects",
        lambda: {
            "M31": {
                "hours": 0,
                "target_hours": 10,
            },
        },
    )

    module.show_portfolio_completion_forecast([
        {
            "night": 1,
            "date": "2026-08-23",
            "project": "M31",
            "hours": 4,
            "target_hours": 10,
            "remaining_after": 6,
        },
    ])

    output = capsys.readouterr().out

    assert (
        "Date de fin estimée : hors horizon prévisionnel"
        in output
    )
    assert "Dernière nuit connue : 2026-08-23" in output


def test_completed_portfolio_reports_completion_date(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        module,
        "get_projects",
        lambda: {
            "M31": {
                "hours": 0,
                "target_hours": 4,
            },
        },
    )

    module.show_portfolio_completion_forecast([
        {
            "night": 1,
            "date": "2026-08-23",
            "project": "M31",
            "hours": 4,
            "target_hours": 4,
            "remaining_after": 0,
        },
    ])

    output = capsys.readouterr().out

    assert "Date de fin estimée : 2026-08-23" in output
    assert "hors horizon prévisionnel" not in output
