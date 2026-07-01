from decision.rule_contribution import RuleContribution
from decision.models.sampling_model import SamplingModel

class SamplingRule:
    name = "Sampling"

    def evaluate(self, context, profile):

        sampling = context.get("sampling")

        print("DEBUG object_type :", context.get("object_type"))
        print("DEBUG object_size :", context.get("object_size_arcmin"))
        print("DEBUG seeing :", context.get("seeing"))
        print("DEBUG sampling :", sampling)

        evaluation = SamplingModel.evaluate(
        object_type=context.get("object_type"),
        object_size_arcmin=context.get("object_size_arcmin"),
        seeing_arcsec=context.get("seeing"),
        sampling_arcsec_pixel=sampling,
    )

        if sampling is None:
            return RuleContribution(
                rule=self.name,
                score=0,
                confidence=0.5,
                reason="Sampling inconnu",
                details="Sampling : None",
            )

        score = evaluation.score
        reason = evaluation.diagnostic

        return RuleContribution(
            rule=self.name,
            score=score,
            confidence=1.0,
            reason=reason,
            details=evaluation.suggestion
        )

