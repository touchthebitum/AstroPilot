from decision.rule_contribution import RuleContribution
from decision.rules.sampling_rule import SamplingRule
from decision.rules.seeing_rule import SeeingRule
from astropilot.user_profile import get_rule_weights


class DecisionEngine:

    def __init__(self):
        self.rules = []

    def add_rule(self, rule):
        self.rules.append(rule)

    def evaluate(self, context, profile):
        total_score = 0
        contributions = []

        weights = get_rule_weights()

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

            rule_key = contribution.rule.lower().replace(" ", "_")

            weight = weights.get(rule_key, contribution.weight)
            contribution.weight = weight

            total_score += contribution.score * weight
            contributions.append(contribution)

            

        print("\n===== EXPLICATION DE LA DECISION =====")

        for c in sorted(contributions, key=lambda x: abs(x.score), reverse=True):

            if abs(c.score) <1:
                continue

            signe = "+" if c.score >= 0 else "-"
            print(f"{signe}{abs(c.score):5.1f} | {c.rule}")
            if c.reason:
                print(f"       {c.reason}")

        print("===============================\n")

        return contributions, total_score