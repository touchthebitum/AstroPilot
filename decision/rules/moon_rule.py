from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution
from astropilot.engines.sky_engine import SkyEngine

class MoonRule(BaseRule):

    def evaluate(self, context, profile):

        score = SkyEngine().moon_penalty(
            context["illumination"],
            context["moon_elevation"],
            context["moon_sep"],
        )

        return RuleContribution(
            rule="Moon",
            score=-score,
            reason="Impact lunaire",
            details=f"Pénalité : {score}",
        )
