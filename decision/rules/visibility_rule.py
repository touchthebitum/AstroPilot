from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution

from astropilot.engines.sky_engine import SkyEngine


class VisibilityRule(BaseRule):

    name = "Visibility"

    def evaluate(self, context, profile):

        visibility = context.weather.visibility

        score = -SkyEngine().visibility_penalty(visibility)

        if score == 0:
            reason = "Bonne visibilité"
        elif score >= -5:
            reason = "Visibilité modérée"
        elif score >= -12:
            reason = "Visibilité faible"
        else:
            reason = "Visibilité très faible"

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=f"Visibilité : {visibility / 1000:.1f} km",
        )