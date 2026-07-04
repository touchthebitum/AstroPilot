from decision.risk.risk_report import RiskReport


class RiskEngine:

    @staticmethod
    def evaluate(
        project_priority: int,
        remaining_hours: float,
    ):

        score = 0
        explanation = []

        if project_priority >= 80:
            score += 40
            explanation.append("Projet très prioritaire")

        if remaining_hours >= 10:
            score += 30
            explanation.append("Beaucoup d'heures restantes")

        if score >= 60:
            level = "HIGH"
        elif score >= 30:
            level = "MEDIUM"
        else:
            level = "LOW"

        return RiskReport(
            level=level,
            score=score,
            explanation=explanation,
        )
