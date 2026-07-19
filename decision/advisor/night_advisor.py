from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Advice:
    time: str
    priority: str
    category: str
    message: str


class NightAdvisor:
    @staticmethod
    def build(mission) -> List[Advice]:

        advices: List[Advice] = []

        if mission.productivity.productive_hours < 2:
            advices.append(
                Advice(
                    time="Début",
                    priority="HIGH",
                    category="strategy",
                    message="Fenêtre productive courte : éviter tout changement de cible.",
                )
            )

        if mission.productivity.confidence < 0.40:
            advices.append(
                Advice(
                    time="Avant installation",
                    priority="MEDIUM",
                    category="weather",
                    message="Prévisions peu fiables : vérifier les dernières données météo.",
                )
            )
        if (
            mission.season_analysis is not None
            and mission.season_analysis.data.get("urgency") == "HIGH"
        ):
            advices.append(
                Advice(
                    time="Début",
                    priority="HIGH",
                    category="season",
                    message="Objet proche de la fin de saison : lui donner la priorité.",
                )
            )

        if mission.risk_report in ("HIGH", "CRITICAL"):
            advices.append(
                Advice(
                    time="Début",
                    priority="HIGH",
                    category="risk",
                    message="Commencer immédiatement cette cible afin de réduire le risque de report.",
                )
            )

        if not advices:
            advices.append(
                Advice(
                    time="Début",
                    priority="INFO",
                    category="general",
                    message="Aucun conseil particulier pour cette nuit.",
                )
            )

        return advices