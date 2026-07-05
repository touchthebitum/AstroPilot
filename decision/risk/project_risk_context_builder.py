from decision.risk.project_risk_context import ProjectRiskContext
from decision.season.season_engine import SeasonEngine
import math


class ProjectRiskContextBuilder:

    @staticmethod
    def build(target, context):

        remaining_hours = context.portfolio.total_remaining_hours or 5
        good_nights = SeasonEngine.remaining_good_nights(target)

        average_productive_hours = 4.0

        required_nights = math.ceil(
            remaining_hours / average_productive_hours
        )

        pressure = remaining_hours / max(good_nights, 1)

        return ProjectRiskContext(
            priority=context.portfolio.highest_priority or 50,
            remaining_hours=context.portfolio.total_remaining_hours or 5,
            completion=context.portfolio.average_progress or 0,
            season_remaining_days=SeasonEngine.remaining_days(target),
            favorable_nights=SeasonEngine.remaining_good_nights(target),
            season_urgency=SeasonEngine.urgency_score(target),
            pressure=pressure,
            required_nights=required_nights,
        )