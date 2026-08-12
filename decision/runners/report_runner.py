from __future__ import annotations
from decision.recommendation.recommendation import Recommendation


class ReportRunner:

    def __init__(
        self,
        portfolio_forecast_engine,
        show_portfolio_ranking,
        show_completion_forecast,
        show_astro_calendar,
        simulate_portfolio_calendar,
        show_roadmap,
        show_portfolio_completion_forecast,
        present_mission,
        tonight_mission_service,
    ):
        self.portfolio_forecast_engine = portfolio_forecast_engine
        self.show_portfolio_ranking = show_portfolio_ranking
        self.show_completion_forecast = show_completion_forecast
        self.show_astro_calendar = show_astro_calendar
        self.simulate_portfolio_calendar = simulate_portfolio_calendar
        self.show_roadmap = show_roadmap
        self.show_portfolio_completion_forecast = (
            show_portfolio_completion_forecast)
        self.present_mission = present_mission
        self.tonight_mission_service = tonight_mission_service

    def run_portfolio(self):
        self.show_portfolio_ranking()
        self.show_completion_forecast()

    def run_calendar(self, nights):
        self.show_astro_calendar(nights)
        return self.simulate_portfolio_calendar(nights)

    def run_full(
        self,
        nights,
        night_capacities,
    ):
        self.show_portfolio_ranking()
        self.show_astro_calendar(nights)

        roadmap = self.simulate_portfolio_calendar(nights)

        self.show_roadmap(
            roadmap,
            forecast_engine=self.portfolio_forecast_engine,
            night_capacities=night_capacities,
        )

        dynamic_roadmap = (
            self.portfolio_forecast_engine
            .simulate_dynamic_portfolio_roadmap(
                night_capacities=night_capacities,
            )
        )

        self.show_portfolio_completion_forecast(
            dynamic_roadmap
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
