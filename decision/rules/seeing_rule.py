from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution

class SeeingRule(BaseRule):
    name = "Seeing"

    def evaluate(self, context, profile):
        ...

        return RuleContribution(
        rule=self.name,
        score=0,
        confidence=1.0,
        reason="Seeing non encore évalué",
        details=""
    )