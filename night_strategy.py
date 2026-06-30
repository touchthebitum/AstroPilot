class StrategyType:
    FINISH_PROJECT = "FINISH_PROJECT"
    BALANCED = "BALANCED"
    DISCOVERY = "DISCOVERY"
    ROI_MAX = "ROI_MAX"
    WEATHER_OPPORTUNITY = "WEATHER_OPPORTUNITY"

class NightStrategy:

    def __init__(self, profile=None):
        self.profile = profile

    def compute_strategic_score(self, project):
        score = 0

        score += project.get("roi", 0) * 10
        score += project.get("progress", 0) * 0.5

        remaining = project.get("remaining_hours")
        if remaining is None:
            remaining = 0

        score -= remaining

        score += project.get("season_bonus", 0)
        score += project.get("weather_bonus", 0)

        return score

    def choose_strategy(
        self,
        recommended_objects,
        available_hours,
    ):
        """
        Retourne la stratégie optimale pour cette nuit.
        """
        for p in recommended_objects:
            p["strategic_score"] = self.compute_strategic_score(p)

        recommended_objects = sorted(
            recommended_objects,
            key=lambda p: p["strategic_score"],
            reverse=True,
)
        if not recommended_objects:
            return {
                "strategy": StrategyType.BALANCED,
                "projects": [],
                "reason": "Aucun projet disponible.",
                "confidence": 0.0,
                "expected_roi": None,
            }

        finish_candidates = [
        p for p in recommended_objects
        if p.get("progress", 0) >= 85
        ]

        if finish_candidates:
            best = finish_candidates[0]
        else:
            best = recommended_objects[0]

        remaining = best.get("remaining_hours", 999)
        progress = best.get("progress", 0)
        roi = best.get("roi", 0)

        if progress >= 85:
            strategy = StrategyType.FINISH_PROJECT
            reason = "Projet presque terminé."

        elif roi >= 8:
            strategy = StrategyType.ROI_MAX
            reason = "ROI exceptionnel."

        else:
            strategy = StrategyType.BALANCED
            reason = "Compromis entre rendement et progression."

        if strategy in (
            StrategyType.FINISH_PROJECT,
            StrategyType.ROI_MAX,
        ):
            selected_projects = [best]
        else:
            selected_projects = recommended_objects

        return {
            "strategy": strategy,
            "projects": selected_projects,
            "available_hours": available_hours,
            "reason": reason,
            "confidence": 0.85,
            "expected_roi": roi,
        }

if __name__ == "__main__":

    strategy = NightStrategy()

    result = strategy.choose_strategy(
        [
            {"name": "IC1396"},
            {"name": "M31"}
        ],
        4.0
    )

    print("\n===== NIGHT STRATEGY =====")
    print(f"Stratégie : {result['strategy']}")
    print(f"Confiance : {result['confidence']:.0%}")
    print(f"Raison : {result['reason']}")
    print("Projets :")
    for p in result["projects"]:
        print(f" - {p['name']}")


    def compute_strategic_score(self, project):
        """
        Calcule le score stratégique d'un projet.
        """

        score = 0

        score += project.get("roi", 0) * 10
        score += project.get("progress", 0) * 0.5

        score -= project.get("remaining_hours", 0)

        score += project.get("season_bonus", 0)
        score += project.get("weather_bonus", 0)

        return score