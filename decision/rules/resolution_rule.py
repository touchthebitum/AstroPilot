from decision.rule_contribution import RuleContribution
from decision.models.resolution_model import ResolutionModel
from decision.calculators.setup_calculator import SetupCalculator



class ResolutionRule:

    name = "Resolution"

    def evaluate(self, context, profile):

        capabilities = SetupCalculator.compute(context.equipment.setup)

        resolution = ResolutionModel.evaluate(
            object_type=context.sky.target.object_type,
            object_size_arcmin=context.sky.target.angular_size_arcmin,
            pixel_size = capabilities.sampling_arcsec_per_pixel
        )

        return RuleContribution(
            rule=self.name,
            score=resolution.score,
            confidence=1.0,
            reason=resolution.diagnostic,
            details=resolution.suggestion,
        )
