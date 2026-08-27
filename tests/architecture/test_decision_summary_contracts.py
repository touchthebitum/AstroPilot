from decision.engines.decision_summary_engine import DecisionSummaryEngine
from decision.models.decision_summary import DecisionSummary
from decision.rule_contribution import RuleContribution


def _contribution(score, reason):
    return RuleContribution(
        rule="Test",
        score=score,
        reason=reason,
    )


def test_summary_classifies_contributions_and_preserves_order():
    contributions = [
        _contribution(12, "Altitude excellente"),
        _contribution(-4, "Lune présente"),
        _contribution(8, "Bon cadrage"),
        _contribution(0, "Impact neutre"),
        _contribution(7.99, "Presque positif"),
        _contribution(-10, "Vent fort"),
    ]

    summary = DecisionSummaryEngine.build(contributions)

    assert summary.title == "Pourquoi cette recommandation ?"
    assert summary.confidence == 1.0
    assert summary.positives == ["Altitude excellente", "Bon cadrage"]
    assert summary.negatives == ["Lune présente", "Vent fort"]
    assert summary.recommendations == []


def test_summary_positive_threshold_is_inclusive_at_eight():
    below = DecisionSummaryEngine.build([_contribution(7.99, "below")])
    exact = DecisionSummaryEngine.build([_contribution(8.0, "exact")])

    assert below.positives == []
    assert exact.positives == ["exact"]


def test_summary_negative_threshold_is_strictly_below_zero():
    zero = DecisionSummaryEngine.build([_contribution(0.0, "zero")])
    negative = DecisionSummaryEngine.build(
        [_contribution(-0.01, "negative")],
    )

    assert zero.negatives == []
    assert negative.negatives == ["negative"]


def test_summary_build_does_not_mutate_contributions():
    contributions = [
        _contribution(9, "positive"),
        _contribution(-2, "negative"),
    ]
    original = [vars(contribution).copy() for contribution in contributions]

    DecisionSummaryEngine.build(contributions)

    assert [vars(contribution) for contribution in contributions] == original


def test_summary_instances_have_independent_lists():
    first = DecisionSummaryEngine.build([])
    second = DecisionSummaryEngine.build([])

    first.positives.append("positive")
    first.negatives.append("negative")
    first.recommendations.append("recommendation")

    assert second.positives == []
    assert second.negatives == []
    assert second.recommendations == []


def test_decision_summary_model_defaults_are_independent():
    first = DecisionSummary(title="first", confidence=0.8)
    second = DecisionSummary(title="second", confidence=0.9)

    first.positives.append("positive")

    assert second.positives == []
