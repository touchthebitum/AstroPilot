import pytest

from decision.risk.project_risk_context import ProjectRiskContext
from decision.risk.risk_engine import RiskEngine


def risk_context(**overrides):
    values = {
        "priority": 0,
        "remaining_hours": 10,
        "completion": 0.5,
        "season_remaining_days": None,
        "favorable_nights": None,
        "pressure": 0,
    }
    values.update(overrides)
    return ProjectRiskContext(**values)


@pytest.mark.parametrize(
    ("overrides", "expected_score", "expected_explanation"),
    [
        ({"pressure": 0.10}, 5, "Pression stratégique modérée"),
        ({"pressure": 0.25}, 15, "Pression stratégique élevée"),
        ({"pressure": 0.50}, 25, "Pression stratégique critique"),
        ({"favorable_nights": 7}, 10, "Nombre limité de nuits favorables"),
        ({"favorable_nights": 3}, 20, "Peu de nuits favorables restantes"),
        ({"season_remaining_days": 30}, 10, "Saison à surveiller"),
        ({"season_remaining_days": 14}, 20, "Fin de saison proche"),
        ({"priority": 50}, 20, "Projet modérément prioritaire"),
        ({"priority": 80}, 40, "Projet très prioritaire"),
    ],
)
def test_each_risk_threshold_contributes_to_the_score(
    overrides,
    expected_score,
    expected_explanation,
):
    report = RiskEngine.evaluate(risk_context(**overrides))

    assert report.score == expected_score
    assert report.explanation == [expected_explanation]


@pytest.mark.parametrize(
    ("overrides", "expected_score", "expected_level"),
    [
        ({}, 0, "LOW"),
        ({"priority": 50, "favorable_nights": 7}, 30, "MEDIUM"),
        ({"priority": 80, "favorable_nights": 3}, 60, "HIGH"),
    ],
)
def test_score_maps_to_the_expected_risk_level(
    overrides,
    expected_score,
    expected_level,
):
    report = RiskEngine.evaluate(risk_context(**overrides))

    assert report.score == expected_score
    assert report.level == expected_level


def test_missing_season_data_is_neutral_and_context_is_preserved():
    context = risk_context(
        season_remaining_days=None,
        favorable_nights=None,
        pressure=None,
    )

    report = RiskEngine.evaluate(context)

    assert report.score == 0
    assert report.level == "LOW"
    assert report.explanation == []
    assert report.context is context


def test_combined_critical_factors_are_accumulated_with_explanations():
    report = RiskEngine.evaluate(
        risk_context(
            priority=80,
            season_remaining_days=14,
            favorable_nights=3,
            pressure=0.50,
        )
    )

    assert report.score == 105
    assert report.level == "HIGH"
    assert report.explanation == [
        "Pression stratégique critique",
        "Peu de nuits favorables restantes",
        "Fin de saison proche",
        "Projet très prioritaire",
    ]
