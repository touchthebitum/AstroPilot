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
        profile=None,
    ):
        simulation_kwargs = {"night_capacities": night_capacities}
        if profile is not None:
            simulation_kwargs["profile"] = profile
        dynamic_roadmap = self.portfolio_forecast_engine.simulate_dynamic_portfolio_roadmap(**simulation_kwargs)

        presentation_kwargs = {}
        if profile is not None:
            presentation_kwargs["projects"] = profile.get("projects", {})
        self.report_runner.show_portfolio_completion_forecast(
            dynamic_roadmap,
            **presentation_kwargs,
        )

    def present_recommended_mission(
        self,
        winner,
        top_objects,
        top_nights,
        profile=None,
    ):
        available_hours = winner.get(
            "duration",
            3.0,
        )

        recommendation_kwargs = {"available_hours": available_hours}
        if profile is not None:
            recommendation_kwargs["profile"] = profile
        recommended_projects = self.recommend_project_for_night(
            top_objects,
            **recommendation_kwargs,
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

        self.report_runner.run_tonight(
            winner=winner,
            objects=top_objects,
            recommendation=recommendation,
            build_mission_input=(
                self.build_mission_input
                if profile is None
                else lambda evaluation: self.build_mission_input(
                    evaluation,
                    profile=profile,
                )
            ),
            top_nights=top_nights,
        )

    def run(
        self,
        top_nights,
        night_capacities,
        profile=None,
    ):
        if not top_nights:
            return

        winner = top_nights[0]
        top_objects = winner.get("top_objects") or []

        self.present_recommended_mission(
            winner=winner,
            top_objects=top_objects,
            top_nights=top_nights,
            profile=profile,
        )

        self.show_completion_forecast(
            night_capacities,
            profile,
        )
