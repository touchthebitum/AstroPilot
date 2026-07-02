from decision.rule_contribution import RuleContribution
from decision.models.resolution_model import ResolutionModel


class ResolutionRule:

    name = "Resolution"

    def evaluate(self, context, profile):

        print("DEBUG RESOLUTION RULE CALLED")

        resolution = ResolutionModel.evaluate(
            object_type=context.get("object_type"),
            object_size_arcmin=context.get("object_size_arcmin"),
            pixel_size=context.get("sampling"),
        )

        return RuleContribution(
            rule=self.name,
            score=resolution.score,
            confidence=1.0,
            reason=resolution.diagnostic,
            details=resolution.suggestion,
        )
