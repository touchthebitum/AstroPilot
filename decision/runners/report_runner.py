from __future__ import annotations
from decision.recommendation.recommendation import Recommendation


class ReportRunner:

    def __init__(
        self,
        portfolio_forecast_engine,
        show_multi_night_portfolio_roadmap,
        show_portfolio_completion_forecast,
        present_mission,
        tonight_mission_service,
    ):
        self.portfolio_forecast_engine = portfolio_forecast_engine
        self.show_multi_night_portfolio_roadmap = (
            show_multi_night_portfolio_roadmap
    )
        self.show_portfolio_completion_forecast = (
            show_portfolio_completion_forecast
        )
        self.present_mission = present_mission
        self.tonight_mission_service = tonight_mission_service

    def run_portfolio(
        self,
        night_capacities,
        profile=None,
        **completion_kwargs,
    ):
        simulation_kwargs = {"night_capacities": night_capacities}
        if profile is not None:
            simulation_kwargs["profile"] = profile
        dynamic_roadmap = self.portfolio_forecast_engine.simulate_dynamic_portfolio_roadmap(**simulation_kwargs)

        if profile is not None:
            completion_kwargs["projects"] = profile.get("projects", {})
        self.show_portfolio_completion_forecast(
            dynamic_roadmap,
            **completion_kwargs,
        )

    def run_calendar(
        self,
        night_capacities,
        profile=None,
    ):
        simulation_kwargs = {"night_capacities": night_capacities}
        if profile is not None:
            simulation_kwargs["profile"] = profile
        roadmap = self.portfolio_forecast_engine.simulate_dynamic_portfolio_roadmap(**simulation_kwargs)

        self.show_multi_night_portfolio_roadmap(
            roadmap
        )

        return roadmap

    def run_full(
        self,
        night_capacities,
        profile=None,
        **completion_kwargs,
    ):
        simulation_kwargs = {"night_capacities": night_capacities}
        if profile is not None:
            simulation_kwargs["profile"] = profile
        roadmap = self.portfolio_forecast_engine.simulate_dynamic_portfolio_roadmap(**simulation_kwargs)

        self.show_multi_night_portfolio_roadmap(
            roadmap
        )

        if profile is not None:
            completion_kwargs["projects"] = profile.get("projects", {})
        self.show_portfolio_completion_forecast(
            roadmap,
            **completion_kwargs,
        )

    def run_tonight(
        self,
        top_nights,
        winner=None,
        objects=None,
        recommendation: Recommendation | None = None,
        build_mission_input=None,
    ):
        mission = None
        recommended_key = None

        if recommendation is not None:
            candidate = recommendation.opportunity.candidate

            recommended_key = candidate.get(
                "catalog_key",
                candidate.get("name"),
            )

        if (
            winner is not None
            and objects is not None
            and recommended_key is not None
            and build_mission_input is not None
        ):
            mission = self.tonight_mission_service.create(
                winner=winner,
                objects=objects,
                recommended_key=recommended_key,
                build_mission_input=build_mission_input,
            )

        if mission is not None:
            self.present_mission(mission)
