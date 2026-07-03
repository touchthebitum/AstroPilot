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
            reason = "Seeing excellent"

        elif seeing <= 1.8:
            score = 10
            reason = "Très bon seeing"

        elif seeing <= 2.3:
            score = 5
            reason = "Bon seeing"

        elif seeing <= 3.0:
            score = 0
            reason = "Seeing moyen"

        else:
            score = -10
            reason = "Seeing médiocre"

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=f'Seeing : {seeing:.1f}"',
        )
