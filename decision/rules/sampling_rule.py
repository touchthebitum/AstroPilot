from decision.rule_contribution import RuleContribution
from decision.models.sampling_model import SamplingModel
from decision.models.resolution_model import ResolutionModel

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

        resolution = ResolutionModel.evaluate(
            object_type=context.get("object_type"),
            object_size_arcmin=context.get("object_size_arcmin"),
            pixel_size=sampling,
        )

        print(
            f"DEBUG RESOLUTION | "
            f"pixels={resolution.pixels:.0f} | "
            f"factor={resolution.size_factor}"
        )

        evaluation = SamplingModel.evaluate(
            object_type=context.get("object_type"),
            object_size_arcmin=context.get("object_size_arcmin"),
            seeing_arcsec=context.get("seeing"),
            sampling_arcsec_pixel=sampling,
            object_name=context.get("object_name"),
        )

        return RuleContribution(
            rule=self.name,
            score=evaluation.score,
            confidence=1.0,
            reason=evaluation.diagnostic,
            details=evaluation.suggestion,
        )

