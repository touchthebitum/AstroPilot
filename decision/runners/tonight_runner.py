from __future__ import annotations

class TonightRunner:

    def __init__(
        self,
        report_runner,
        portfolio_forecast_engine,
        build_mission_input,
        recommend_project_for_night,
        opportunity_recommendation_service,
    ):
        self.report_runner = report_runner
        self.portfolio_forecast_engine = (
            portfolio_forecast_engine
        )
        self.build_mission_input = (
            build_mission_input
        )
        self.recommend_project_for_night = (
            recommend_project_for_night
        )
        self.opportunity_recommendation_service = (
            opportunity_recommendation_service
        )

    def show_completion_forecast(
        self,
        night_capacities,
    ):
        dynamic_roadmap = (
            self.portfolio_forecast_engine
            .simulate_dynamic_portfolio_roadmap(
                night_capacities=night_capacities,
            )
        )

        self.report_runner.show_portfolio_completion_forecast(
            dynamic_roadmap
        )

    def present_recommended_mission(
        self,
        winner,
        top_objects,
        top_nights,
        use_legacy_report,
    ):
        available_hours = winner.get(
            "duration",
            3.0,
        )

        recommended_projects = (
            self.recommend_project_for_night(
                top_objects,
                available_hours=available_hours,
            )
        )

        if not recommended_projects:
            return

        recommendation = (
            self.opportunity_recommendation_service.build(
                candidates=recommended_projects,
            )
        )

        if recommendation is None:
            return

        recommended_project = (
            recommendation.opportunity.candidate
        )
        recommended_key = recommended_project.get(
            "catalog_key",
            recommended_project.get("name"),
        )

        self.report_runner.run_tonight(
            winner=winner,
            objects=top_objects,
            recommended_key=recommended_key,
            build_mission_input=self.build_mission_input,
            top_nights=top_nights,
            use_legacy_report=use_legacy_report,
        )

    def run(
        self,
        top_nights,
        night_capacities,
        use_legacy_report,
    ):
        if not top_nights:
            return

        winner = top_nights[0]
        top_objects = winner.get("top_objects") or []

        self.present_recommended_mission(
            winner=winner,
            top_objects=top_objects,
            top_nights=top_nights,
            use_legacy_report=use_legacy_report,
        )

        self.show_completion_forecast(
            night_capacities
        )