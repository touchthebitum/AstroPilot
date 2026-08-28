import decision.portfolio.portfolio_presenter as module


def projects_with_target(target_hours):
    return {
        "M31": {
            "hours": 0,
            "target_hours": target_hours,
        },
    }


def test_incomplete_portfolio_reports_completion_beyond_horizon(
    capsys,
):
    module.show_portfolio_completion_forecast(
        [{
            "night": 1,
            "date": "2026-08-23",
            "project": "M31",
            "hours": 4,
            "target_hours": 10,
            "remaining_after": 6,
        }],
        projects=projects_with_target(10),
    )

    output = capsys.readouterr().out

    assert "Date de fin estimée : indisponible" in output
    assert "Dernière nuit connue : 2026-08-23" in output


def test_completed_portfolio_reports_completion_date(
    capsys,
):
    module.show_portfolio_completion_forecast(
        [{
            "night": 1,
            "date": "2026-08-23",
            "project": "M31",
            "hours": 4,
            "target_hours": 4,
            "remaining_after": 0,
        }],
        projects=projects_with_target(4),
    )

    output = capsys.readouterr().out

    assert "Date de fin prévue : 2026-08-23" in output
    assert (
        "Basée sur les prévisions météo disponibles."
        in output
    )
    assert "Date de fin estimée" not in output

def test_incomplete_portfolio_extrapolates_completion_from_profile(
    capsys,
):
    module.show_portfolio_completion_forecast(
        [
            {
                "night": 1,
                "date": "2026-08-29",
                "project": "M31",
                "hours": 4,
                "target_hours": 39,
                "remaining_after": 35,
            },
        ],
        projects=projects_with_target(39),
        productive_hours_per_night=4.0,
        observing_nights_per_week=2.0,
        night_capacity_source="profile",
        historical_nights=0,
    )

    output = capsys.readouterr().out

    assert (
        "Date de fin estimée : vers le 2026-09-29"
        in output
    )
    assert (
        "Extrapolation au-delà de l'horizon météo de 7 nuits."
        in output
    )
    assert (
        "Base : 4.0 h/nuit profil × 2.0 nuits/semaine"
        in output
    )
    assert (
        "Confiance : FAIBLE — paramètres du profil"
        in output
    )

def test_incomplete_portfolio_extrapolates_completion_from_history(
    capsys,
):
    module.show_portfolio_completion_forecast(
        [
            {
                "night": 1,
                "date": "2026-08-29",
                "project": "M31",
                "hours": 4,
                "target_hours": 39,
                "remaining_after": 35,
            },
        ],
        projects=projects_with_target(39),
        productive_hours_per_night=3.2,
        observing_nights_per_week=2.0,
        night_capacity_source="history",
        historical_nights=7,
    )

    output = capsys.readouterr().out

    assert (
        "Date de fin estimée : vers le 2026-10-07"
        in output
    )
    assert (
        "Base : 3.2 h/nuit historique × 2.0 nuits/semaine"
        in output
    )
    assert (
        "Confiance : MOYENNE — basée sur 7 nuits observées"
        in output
    )
