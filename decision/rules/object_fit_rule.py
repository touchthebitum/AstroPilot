from decision.engines.object_fit_engine import ObjectFitEngine
from decision.rule_contribution import RuleContribution
from decision.rules.base_rule import BaseRule
    
class ObjectFitRule(BaseRule):

    def evaluate(self, context, profile):

        if not hasattr(context, "sky"):
            return None

        result = ObjectFitEngine.evaluate(context)

        occupation = result.metrics.get("occupation_percent", 0)

        if occupation >= 80:
            reason = f"Le cadrage est idéal : l'objet occupe {occupation:.0f} % du champ."
        elif occupation >= 50:
            reason = f"Cadrage optimal : l'objet occupe {occupation:.0f} % du champ."
        elif occupation >= 25:
            reason = f"Cadrage correct : l'objet occupe {occupation:.0f} % du champ."
        else:
            reason = f"Objet assez petit pour ce setup : seulement {occupation:.0f} % du champ."

        return RuleContribution(
            rule="Object Fit",
            score=result.score * 0.15,
            weight=1.0,
            reason=reason,
            details=f"Occupation : {occupation:.1f} %",
        )