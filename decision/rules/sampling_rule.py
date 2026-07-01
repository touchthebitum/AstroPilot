from decision.rule_contribution import RuleContribution
from decision.models.sampling_model import SamplingModel

class SamplingRule:
    name = "Sampling"

    def evaluate(self, context, profile):

        sampling = context.get("sampling")

        if sampling is None:
            return RuleContribution(
                rule=self.name,
                score=0,
                confidence=0.5,
                reason="Sampling inconnu",
                details="Sampling : None",
            )

        if sampling < 0.6:
            score = -8
            reason = "Sur-échantillonnage"

        elif sampling < 1.5:
            score = 8
            reason = "Excellent sampling"

        elif sampling < 2.5:
            score = 5
            reason = "Bon sampling"

        elif sampling < 4:
            score = 2
            reason = "Sampling correct"

        else:
            score = -5
            reason = "Sous-échantillonnage"

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=f"Sampling : {sampling:.2f}\"/pixel",
        )

