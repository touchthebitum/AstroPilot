from __future__ import annotations


class TonightRunner:

    def __init__(
        self,
        report_runner,
        portfolio_forecast_engine,
        build_mission_input,
    ):
        self.report_runner = report_runner
        self.portfolio_forecast_engine = (
            portfolio_forecast_engine
        )
        self.build_mission_input = (
            build_mission_input
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