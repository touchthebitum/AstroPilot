from math import isfinite

from decision.rule_contribution import RuleContribution
from decision.rules.sampling_rule import SamplingRule
from decision.rules.seeing_rule import SeeingRule


class DecisionEngine:

    def __init__(self):
        self.rules = []

    def add_rule(self, rule):
        self.rules.append(rule)

    def evaluate(self, context, profile):
        total_score = 0
        contributions = []

        weights = profile.get("decision_weights", {})

        for rule in self.rules:

            contribution = rule.evaluate(context, profile)

            if contribution is None:
                continue

            rule_key = contribution.rule.lower().replace(" ", "_")

            weight = weights.get(rule_key, contribution.weight)
            # Match profile ingress for evidence-aware internal callers too.
            if contribution.evidence_status is not None and (
                isinstance(weight, bool) or not isinstance(weight, (int, float))
                or not isfinite(weight) or weight < 0
            ):
                raise ValueError("evidence rule weight must be finite and non-negative")
            contribution.weight = weight

            total_score += contribution.score * weight
            contributions.append(contribution)

        return contributions, total_score
