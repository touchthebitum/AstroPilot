from decision.rule_contribution import RuleContribution
from decision.engines.image_quality_engine import ImageQualityEngine


class ImageQualityRule:

    name = "ImageQuality"

    def evaluate(self, context, profile):

        result = ImageQualityEngine.evaluate(context)

        return RuleContribution(
            rule=self.name,
            score=result.score,
            confidence=1.0,
            reason=f"Qualité image : {result.score:.1f}",
            details=result.recommendation,
        )