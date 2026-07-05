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
        season_urgency = context.season_urgency or 0

        if season_remaining_days is None:
            season_remaining_days = 999

        if favorable_nights is None:
            favorable_nights = 999

        score = 0
        explanation = []

        if season_urgency >= 70:
            score += 20
            explanation.append("Urgence saisonnière élevée")
        elif season_urgency >= 40:
            score += 10
            explanation.append("Urgence saisonnière modérée")

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

        if remaining_hours >= 10:
            score += 30
            explanation.append("Beaucoup d'heures restantes")
        elif remaining_hours >= 5:
            score += 15
            explanation.append("Quelques heures restantes")

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
