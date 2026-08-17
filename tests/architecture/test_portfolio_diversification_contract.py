import decision.portfolio.diversification as diversification
import decision.portfolio.project_state as project_state_module


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
        "get_projects",
        lambda: projects,
    )
    monkeypatch.setattr(
        diversification,
        "CATALOG",
        catalog,
    )
    monkeypatch.setattr(
        project_state_module,
        "get_projects",
        lambda: projects,
    )


def test_portfolio_category_load_uses_remaining_hours(
    monkeypatch,
):
    install_projects(monkeypatch)

    assert diversification.portfolio_category_load() == {
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
        "get_projects",
        lambda: projects,
    )
    monkeypatch.setattr(
        diversification,
        "CATALOG",
        catalog,
    )
    monkeypatch.setattr(
        project_state_module,
        "get_projects",
        lambda: projects,
    )

    assert diversification.diversification_bonus("M31") == 8