from decision.risk.risk_report import RiskReport
from decision.risk.project_risk_context import ProjectRiskContext


class RiskEngine:

    @staticmethod
    def evaluate(
        context: ProjectRiskContext,
    ):

        priority = context.priority
        remaining_hours = context.remaining_hours
        completion = context.completion
        season_remaining_days = context.season_remaining_days
        favorable_nights = context.favorable_nights
        pressure = context.pressure or 0

        if season_remaining_days is None:
            season_remaining_days = 999

        if favorable_nights is None:
            favorable_nights = 999

        score = 0
        explanation = []

        if pressure >= 0.50:
            score += 25
            explanation.append("Pression stratégique critique")
        elif pressure >= 0.25:
            score += 15
            explanation.append("Pression stratégique élevée")
        elif pressure >= 0.10:
            score += 5
            explanation.append("Pression stratégique modérée")

        if favorable_nights <= 3:
            score += 20
            explanation.append("Peu de nuits favorables restantes")

        elif favorable_nights <= 7:
            score += 10
            explanation.append("Nombre limité de nuits favorables")

        if season_remaining_days <= 14:
            score += 20
            explanation.append("Fin de saison proche")

        elif season_remaining_days <= 30:
            score += 10
            explanation.append("Saison à surveiller")

        if priority >= 80:
            score += 40
            explanation.append("Projet très prioritaire")
        elif priority >= 50:
            score += 20
            explanation.append("Projet modérément prioritaire")

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
            context=context,
        )
