from decision.risk.project_risk_context import ProjectRiskContext
from decision.season.season_engine import SeasonEngine


class ProjectRiskContextBuilder:

    @staticmethod
    def build(target, context):

        return ProjectRiskContext(
            priority=context.portfolio.highest_priority or 50,
            remaining_hours=context.portfolio.total_remaining_hours or 5,
            completion=context.portfolio.average_progress or 0,
            season_remaining_days=SeasonEngine.remaining_days(target),
            favorable_nights=SeasonEngine.remaining_good_nights(target),
            season_urgency=SeasonEngine.urgency_score(target),
        )