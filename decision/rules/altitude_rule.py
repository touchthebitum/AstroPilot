from decision.rules.base_rule import BaseRule
from decision.rule_contribution import RuleContribution


class AltitudeRule(BaseRule):
    """
    Évalue l'impact de l'altitude de la cible.
    """

    def evaluate(self, project, context):

        altitude = project.sky.target_altitude_deg

        if altitude >= 70:
            return RuleContribution(
                rule="Altitude",
                score=15,
                reason="Altitude excellente",
                details=f"Altitude : {altitude:.1f}°"
            )

        elif altitude >= 50:
            return RuleContribution(
                rule="Altitude",
                score=8,
                reason="Bonne altitude",
                details=f"Altitude : {altitude:.1f}°"
            )

        elif altitude >= 30:
            return RuleContribution(
                rule="Altitude",
                score=0,
                reason="Altitude correcte",
                details=f"Altitude : {altitude:.1f}°"
            )

        return RuleContribution(
            rule="Altitude",
            score=-15,
            reason="Objet trop bas",
            details=f"Altitude : {altitude:.1f}°"
        )
