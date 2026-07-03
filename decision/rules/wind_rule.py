from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution

from astropilot.engines.sky_engine import SkyEngine


class WindRule(BaseRule):

    name = "Wind"

    def evaluate(self, context, profile):

        wind = context.weather.wind_speed_kmh

        score = -SkyEngine().wind_penalty(wind)

        if score == 0:
            reason = "Vent faible"
        elif score >= -5:
            reason = "Vent modéré"
        elif score >= -12:
            reason = "Vent fort"
        else:
            reason = "Vent très fort"

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=f"Vent : {wind:.1f} km/h",
        )