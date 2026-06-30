from decision.rule_contribution import RuleContribution


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

            if contribution is None:
                continue

            total_score += contribution.score * contribution.weight
            contributions.append(contribution)

        return contributions, total_score