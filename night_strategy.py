class NightStrategy:

    def __init__(self, profile=None):
        self.profile = profile

    def choose_strategy(
        self,
        recommended_objects,
        available_hours,
    ):
        """
        Retourne la stratégie optimale pour cette nuit.
        """

        if not recommended_objects:
            return {
                "strategy": "NONE",
                "projects": []
            }

        strategy = {
            "strategy": "BALANCED",
            "projects": recommended_objects,
            "available_hours": available_hours
        }

        return strategy

if __name__ == "__main__":

    strategy = NightStrategy()

    result = strategy.choose_strategy(
        [
            {"name": "IC1396"},
            {"name": "M31"}
        ],
        4.0
    )

    print(result)