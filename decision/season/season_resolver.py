from dataclasses import asdict

from decision.season.dynamic_season_engine import (
    DynamicSeasonEngine,
)


class SeasonResolver:

    @staticmethod
    def resolve(context):
        dynamic = DynamicSeasonEngine.summary(context)

        if (
            dynamic.remaining_days is None
            or dynamic.remaining_good_nights is None
        ):
            return {
                "target": context.target,
                "start_date": None,
                "end_date": None,
                "peak_date": None,
                "remaining_days": None,
                "remaining_good_nights": None,
                "urgency": "UNKNOWN",
                "urgency_score": 0,
                "source": "unknown",
                "confidence": 0.0,
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