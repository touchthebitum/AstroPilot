from types import SimpleNamespace

import pytest

from decision.advisor.night_advisor import Advice, NightAdvisor


def mission(
    *,
    productive_hours=3,
    confidence=0.8,
    season_urgency=None,
    risk_report="LOW",
):
    season_analysis = (
        None
        if season_urgency is None
        else SimpleNamespace(data={"urgency": season_urgency})
    )

    return SimpleNamespace(
        productivity=SimpleNamespace(
            productive_hours=productive_hours,
            confidence=confidence,
        ),
        season_analysis=season_analysis,
        risk_report=risk_report,
    )


@pytest.mark.parametrize(
    ("productive_hours", "expected_categories"),
    [
        (1.99, ["strategy"]),
        (2.0, ["general"]),
    ],
)
def test_short_productive_window_threshold(
    productive_hours,
    expected_categories,
):
    advices = NightAdvisor.build(
        mission(productive_hours=productive_hours)
    )

    assert [advice.category for advice in advices] == expected_categories


@pytest.mark.parametrize(
    ("confidence", "expected_categories"),
    [
        (0.39, ["weather"]),
        (0.40, ["general"]),
    ],
)
def test_weather_confidence_threshold(
    confidence,
    expected_categories,
):
    advices = NightAdvisor.build(mission(confidence=confidence))

    assert [advice.category for advice in advices] == expected_categories


def test_only_high_season_urgency_adds_season_advice():
    high = NightAdvisor.build(mission(season_urgency="HIGH"))
    medium = NightAdvisor.build(mission(season_urgency="MEDIUM"))
    missing = NightAdvisor.build(mission(season_urgency=None))

    assert [advice.category for advice in high] == ["season"]
    assert [advice.category for advice in medium] == ["general"]
    assert [advice.category for advice in missing] == ["general"]


@pytest.mark.parametrize("risk_report", ["HIGH", "CRITICAL"])
def test_high_and_critical_risks_add_risk_advice(risk_report):
    advices = NightAdvisor.build(mission(risk_report=risk_report))

    assert [advice.category for advice in advices] == ["risk"]
    assert advices[0].priority == "HIGH"


def test_all_applicable_advices_keep_decision_order():
    advices = NightAdvisor.build(
        mission(
            productive_hours=1,
            confidence=0.2,
            season_urgency="HIGH",
            risk_report="CRITICAL",
        )
    )

    assert [advice.category for advice in advices] == [
        "strategy",
        "weather",
        "season",
        "risk",
    ]
    assert all(isinstance(advice, Advice) for advice in advices)


def test_default_advice_is_stable_and_informational():
    assert NightAdvisor.build(mission()) == [
        Advice(
            time="Début",
            priority="INFO",
            category="general",
            message="Aucun conseil particulier pour cette nuit.",
        )
    ]
