from decision.rule_contribution import RuleContribution
from decision.models.sampling_model import SamplingModel
from decision.models.resolution_model import ResolutionModel
from decision.calculators.setup_calculator import SetupCalculator

class SamplingRule:
    name = "Sampling"

    def evaluate(self, context, profile):

        capabilities = SetupCalculator.compute(context.equipment.setup)
        sampling = capabilities.sampling_arcsec_per_pixel

        if sampling is None:
            return RuleContribution(
                rule=self.name,
                score=0,
                confidence=0.5,
                reason="Sampling inconnu",
                details="Sampling : None",
            )

        resolution = ResolutionModel.evaluate(
            object_type = context.sky.target.object_type,
            object_size_arcmin=context.sky.target.angular_size_arcmin,
            pixel_size=sampling,
        )

        print(
            f"DEBUG RESOLUTION | "
            f"pixels={resolution.pixels:.0f} | "
            f"factor={resolution.size_factor}"
        )

        evaluation = SamplingModel.evaluate(
            object_type = context.sky.target.object_type,
            object_size_arcmin=context.sky.target.angular_size_arcmin,
            seeing_arcsec=context.weather.seeing_arcsec,
            sampling_arcsec_pixel=sampling,
            object_name=context.sky.target.name,
        )

        return RuleContribution(
            rule=self.name,
            score=evaluation.score,
            confidence=1.0,
            reason=evaluation.diagnostic,
            details=evaluation.suggestion,
        )

