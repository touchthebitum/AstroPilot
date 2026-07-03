from decision.engines.object_fit_engine import ObjectFitEngine
from decision.rule_contribution import RuleContribution
from decision.rules.base_rule import BaseRule
    
class ObjectFitRule(BaseRule):

    def evaluate(self, context, profile):

        if not hasattr(context, "sky"):
            return None

        result = ObjectFitEngine.evaluate(context)

        return RuleContribution(
            rule="Object Fit",
            score=result.score * 0.15,
            weight=1.0,
            reason=result.explanation,
            details=result.metrics,
        )