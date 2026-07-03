from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution


class CloudRule(BaseRule):

    def evaluate(self, context, profile):

        total = context.weather.cloud_cover

        # Temporaire : nous n'avons pas encore les couches de nuages
        low = total
        mid = total
        high = total

        weighted = (
            low * 0.2 +
            mid * 0.3 +
            high * 0.5
        )

        if weighted < 10:
            penalty = 0
        elif weighted < 20:
            penalty = 3
        elif weighted < 30:
            penalty = 8
        elif weighted < 40:
            penalty = 15
        elif weighted < 60:
            penalty = 22
        elif weighted < 80:
            penalty = 35
        else:
            penalty = 50

        return RuleContribution(
            rule="Cloud",
            score=-penalty,
            confidence=1.0,
            reason="Couverture nuageuse",
            details=f"Nuages pondérés : {weighted:.1f} %",
        )
