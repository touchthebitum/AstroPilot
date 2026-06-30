from decision.rule_contribution import RuleContribution


class DecisionEngine:

    def __init__(self):
        self.rules = []

    def add_rule(self, rule):
        self.rules.append(rule)

    def evaluate(self, project, context):
        contributions = []

        for rule in self.rules:
            result = rule.evaluate(project, context)

            if result is not None:
                contributions.append(result)

        return contributions