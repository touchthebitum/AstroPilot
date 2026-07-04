from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution

class SeeingRule(BaseRule):
    name = "Seeing"

    def evaluate(self, context, profile):

        seeing = context.weather.seeing_arcsec

        if seeing is None:
            return RuleContribution(
                rule=self.name,
                score=0,
                confidence=0.3,
                reason="Seeing indisponible",
                details=f"Seeing : {seeing}",
            )

        if seeing <= 1.2:
            score = 15
            reason = f"Seeing exceptionnel ({seeing:.1f}\")"

        elif seeing <= 1.8:
            score = 10
            reason = f"Très bon seeing ({seeing:.1f}\")"

        elif seeing <= 2.3:
            score = 5
            reason = f"Bon seeing ({seeing:.1f}\")"

        elif seeing <= 3.0:
            score = 0
            reason = f"Seeing moyen ({seeing:.1f}\")"

        else:
            score = -10
            reason = f"Seeing médiocre ({seeing:.1f}\")"

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=""
        )
