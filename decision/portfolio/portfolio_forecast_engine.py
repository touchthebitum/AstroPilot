from __future__ import annotations

import copy

from astropilot.user_profile import get_projects


class PortfolioForecastEngine:


    def __init__(self, future_engine, score_project):
            self.future_engine = future_engine
            self.score_project = score_project

    def simulate_dynamic_portfolio_roadmap(
        self,
        night_capacities=None,
        avg_night_hours=5,
    ):
        projects = copy.deepcopy(get_projects())

        simulated = []
        current_night = 1

        while True:
            if night_capacities and current_night > len(night_capacities):
                break

            if current_night > 50:
                print("STOP sécurité roadmap dynamique")
                break

            if night_capacities:
                capacity = night_capacities[current_night - 1]
                hours_remaining_night = capacity.get(
                    "hours",
                    avg_night_hours,
                )
            else:
                capacity = None
                hours_remaining_night = avg_night_hours

            while hours_remaining_night > 0:
                active_projects = {}

                for name, project in projects.items():
                    remaining = (
                        project["target_hours"]
                        - project["hours"]
                    )

                    if remaining > 0:
                        active_projects[name] = project

                if not active_projects:
                    return simulated

                best_name = None
                best_score = -9999

                for name, project in active_projects.items():

                    remaining = max(
                        0,
                        project["target_hours"]
                        - project["hours"],
                    )

                    future = self.future_engine.estimate(
                        name,
                        remaining_hours=remaining,
                        latitude=(
                            capacity.get("latitude")
                            if capacity
                            else None
                        ),
                        longitude=(
                            capacity.get("longitude")
                            if capacity
                            else None
                        ),
                        observation_time=(
                            capacity.get("observation_time")
                            if capacity
                            else None
                        ),
                    )

                    base_score = self.score_project(
                        project,
                        available_hours=hours_remaining_night,
                    )

                    ratio = future.opportunity_ratio

                    opportunity_bonus = max(
                        0,
                        min(
                            30,
                            round(
                                30 / max(ratio, 0.1),
                                1,
                            ),
                        ),
                    )

                    score = base_score + opportunity_bonus

                    if score > best_score:
                        best_score = score
                        best_name = name

                project = projects[best_name]

                remaining = (
                    project["target_hours"]
                    - project["hours"]
                )

                hours_this_step = min(
                    hours_remaining_night,
                    remaining,
                )

                if hours_this_step <= 0:
                    break

                project["hours"] += hours_this_step
                hours_remaining_night -= hours_this_step

                simulated.append({
                    "night": current_night,
                    "date": (
                        capacity.get("date")
                        if capacity
                        else None
                    ),
                    "capacity": (
                        capacity.get("hours", avg_night_hours)
                        if capacity
                        else avg_night_hours
                    ),
                    "project": best_name,
                    "score": best_score,
                    "hours": hours_this_step,
                    "target_hours": project["target_hours"],
                    "current_hours": project["hours"],
                    "remaining_after": max(
                        0,
                        remaining - hours_this_step,
                    ),
                    "completed": (
                        remaining - hours_this_step <= 0
                    ),
                })

            current_night += 1

        return simulated