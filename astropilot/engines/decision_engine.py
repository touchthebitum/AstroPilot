
from astropilot.domain.recommendation import Recommendation
from astropilot.knowledge_engine import KnowledgeEngine


class DecisionEngine:

    def __init__(self):
        self.knowledge = KnowledgeEngine()

    def recommend(self):

        recommendation = Recommendation(
            target="IC1396",
            confidence=93
        )

        recommendation.add_reason(
            "Excellent objet SHO"
        )

        recommendation.add_reason(
            "La Lune favorise les filtres étroits"
        )

        recommendation.add_reason(
            "Compatible avec un setup grand champ"
        )

        recommendation.add_reason(
            "Projet prioritaire"
        )

        return recommendation
