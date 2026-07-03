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
        for rule in self.rules:

            contribution = rule.evaluate(context, profile)

            if contribution is not None:
                print(
                    f"{contribution.rule:<18}"
                    f" score={contribution.score:>6.1f}"
                    f" poids={contribution.weight:.2f}"
                    f" total={contribution.score * contribution.weight:>6.1f}"
                )

            if contribution is None:
                continue

            total_score += contribution.score * contribution.weight
            contributions.append(contribution)

        return contributions, total_score