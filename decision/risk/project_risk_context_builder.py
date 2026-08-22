from decision.risk.project_risk_context import ProjectRiskContext
from decision.productivity.productivity_engine import ProductivityEngine
from decision.intelligence.analysis_context import AnalysisContext
from decision.season.season_resolver import SeasonResolver


class ProjectRiskContextBuilder:

    @staticmethod
    def build(target, context):

        remaining_hours = (
            context.portfolio.total_remaining_hours
            or 5
        )

        season_context = AnalysisContext(
            target=target,
            latitude=context.site.latitude,
            longitude=context.site.longitude,
            observation_time=context.session.start_time,
        )

        season = SeasonResolver.resolve(
            season_context
        )

        season_remaining_days = season["remaining_days"]
        good_nights = season["remaining_good_nights"]

        productivity = ProductivityEngine.evaluate(
            remaining_hours
        )
        required_nights = productivity.required_nights

        pressure = (
            remaining_hours
            / max(good_nights or 0, 1)
        )

        return ProjectRiskContext(
            priority=(
                context.portfolio.highest_priority
                or 50
            ),
            remaining_hours=remaining_hours,
            completion=(
                context.portfolio.average_progress
                or 0
            ),
            season_remaining_days=season_remaining_days,
            favorable_nights=good_nights,
            pressure=pressure,
            required_nights=required_nights,
        )
