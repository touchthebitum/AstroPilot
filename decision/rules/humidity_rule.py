from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution

from astropilot.engines.sky_engine import SkyEngine


class HumidityRule(BaseRule):

    name = "Humidity"

    def evaluate(self, context, profile):

        humidity = context.get("humidity", 0)

        score = -SkyEngine().humidity_penalty(humidity)

        if score == 0:
            reason = "Humidité idéale"
        elif score >= -5:
            reason = "Humidité modérée"
        elif score >= -12:
            reason = "Humidité élevée"
        else:
            reason = "Humidité très élevée"

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=f"Humidité : {humidity:.0f} %",
        )
