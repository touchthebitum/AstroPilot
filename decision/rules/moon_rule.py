from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution
from astropilot.engines.sky_engine import SkyEngine

class MoonRule(BaseRule):

    def evaluate(self, context, profile):

        score = SkyEngine().moon_penalty(
            context.sky.moon_illumination,
            0,  # moon_elevation temporaire
            context.sky.moon_separation_deg,
)
        return RuleContribution(
            rule="Moon",
            score=-score,
            reason="Impact lunaire",
            details=f"Pénalité : {score}",
        )
