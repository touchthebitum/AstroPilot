from decision.models.decision_summary import DecisionSummary


class DecisionSummaryEngine:

    @staticmethod
    def build(contributions):

        summary = DecisionSummary(
            title="Pourquoi cette recommandation ?",
            confidence=None,
        )

        for c in contributions:

            if c.score >= 8:
                summary.positives.append(c.reason)

            elif c.score < 0:
                summary.negatives.append(c.reason)

        return summary
