import decision.portfolio.diversification as diversification


def install_projects(monkeypatch):
    projects = {
        "M31": {
            "hours": 10,
            "target_hours": 20,
        },
        "Rosette": {
            "hours": 2,
            "target_hours": 12,
        },
    }

    catalog = {
        "M31": {
            "type": "galaxy",
        },
        "Rosette": {
            "type": "emission_nebula",
        },
    }

    monkeypatch.setattr(
        diversification,
        "CATALOG",
        catalog,
    )
    return projects


def test_portfolio_category_load_uses_remaining_hours(
    monkeypatch,
):
    projects = install_projects(monkeypatch)

    assert diversification.portfolio_category_load(projects) == {
        "galaxy": 10.0,
        "emission_nebula": 10.0,
    }


def test_diversification_bonus_rewards_underrepresented_category(
    monkeypatch,
):
    projects = {
        "M31": {
            "hours": 19,
            "target_hours": 20,
        },
        "Rosette": {
            "hours": 0,
            "target_hours": 20,
        },
    }

    catalog = {
        "M31": {
            "type": "galaxy",
        },
        "Rosette": {
            "type": "emission_nebula",
        },
    }

    monkeypatch.setattr(
        diversification,
        "CATALOG",
        catalog,
    )
    assert diversification.diversification_bonus("M31", projects) == 8
