from decision.models.decision_summary import DecisionSummary


class DecisionSummaryEngine:

    @staticmethod
    def build(contributions):

        summary = DecisionSummary(
            title="Pourquoi cette recommandation ?",
            confidence=1.0,
        )

        for c in contributions:

            if c.score >= 8:
                summary.positives.append(c.reason)

            elif c.score < 0:
                summary.negatives.append(c.reason)


        print("\n===== POURQUOI CETTE RECOMMANDATION ? =====")

        for p in summary.positives:
            print(f"✓ {p}")

        for n in summary.negatives:
            print(f"⚠ {n}")
            
        return summary