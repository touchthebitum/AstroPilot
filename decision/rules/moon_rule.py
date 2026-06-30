from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution


class MoonRule(BaseRule):

    def evaluate(self, context, profile):

        return RuleContribution(
            rule="Moon",
            score=0,
            reason="MoonRule active",
            details="Test",
        )