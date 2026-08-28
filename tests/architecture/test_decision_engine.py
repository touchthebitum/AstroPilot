from decision.decision_engine import DecisionEngine
from decision.rule_contribution import RuleContribution


class StubRule:
    def __init__(self, contribution):
        self.contribution = contribution
        self.calls = []

    def evaluate(self, context, profile):
        self.calls.append((context, profile))
        return self.contribution


def test_rules_are_evaluated_in_order_and_receive_the_same_inputs():
    context = object()
    profile = {}
    first_contribution = RuleContribution(rule="First", score=10, weight=2)
    third_contribution = RuleContribution(rule="Third", score=5, weight=3)
    first_rule = StubRule(first_contribution)
    skipped_rule = StubRule(None)
    third_rule = StubRule(third_contribution)
    engine = DecisionEngine()

    engine.add_rule(first_rule)
    engine.add_rule(skipped_rule)
    engine.add_rule(third_rule)

    contributions, total_score = engine.evaluate(context, profile)

    assert engine.rules == [first_rule, skipped_rule, third_rule]
    assert first_rule.calls == [(context, profile)]
    assert skipped_rule.calls == [(context, profile)]
    assert third_rule.calls == [(context, profile)]
    assert contributions == [first_contribution, third_contribution]
    assert total_score == 35


def test_contribution_weight_is_used_when_profile_has_no_override():
    contribution = RuleContribution(
        rule="Cloud",
        score=8,
        weight=1.5,
    )
    engine = DecisionEngine()
    engine.add_rule(StubRule(contribution))

    contributions, total_score = engine.evaluate(object(), {})

    assert contributions == [contribution]
    assert contribution.weight == 1.5
    assert total_score == 12


def test_profile_weight_overrides_contribution_weight_by_normalized_rule_name(
):
    contribution = RuleContribution(
        rule="Image Quality",
        score=80,
        weight=2,
    )
    engine = DecisionEngine()
    engine.add_rule(StubRule(contribution))

    contributions, total_score = engine.evaluate(
        object(),
        {"decision_weights": {"image_quality": 0.25}},
    )

    assert contributions == [contribution]
    assert contribution.weight == 0.25
    assert total_score == 20


def test_engine_without_rules_returns_an_empty_result():
    contributions, total_score = DecisionEngine().evaluate(object(), {})

    assert contributions == []
    assert total_score == 0
