from dataclasses import asdict

from decision.season.dynamic_season_engine import (
    DynamicSeasonEngine,
)
from decision.season.season_engine import SeasonEngine


class SeasonResolver:

    @staticmethod
    def resolve(context):
        dynamic = DynamicSeasonEngine.summary(context)

        if (
            dynamic.remaining_days is None
            or dynamic.remaining_good_nights is None
        ):
            legacy = SeasonEngine.summary(
                context.target
            )

            return {
                **legacy,
                "source": "legacy",
                "confidence": None,
            }

        result = asdict(dynamic)

        result["target"] = context.target
        result["urgency_score"] = (
            100
            if dynamic.urgency == "HIGH"
            else 60
            if dynamic.urgency == "MEDIUM"
            else 0
        )
        result["source"] = "dynamic"

        return result