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

        print("===== RULES =====")
        for rule in self.rules:
            print(rule.__class__.__name__)
        print("=================")

        for rule in self.rules:
            print(f"--> {rule.__class__.__name__}")

            contribution = rule.evaluate(context, profile)

            print(f"<-- {rule.__class__.__name__}")

            if contribution is None:
                continue

            total_score += contribution.score * contribution.weight
            contributions.append(contribution)

        return contributions, total_score