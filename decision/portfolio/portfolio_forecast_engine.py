from __future__ import annotations

import copy

from astropilot.user_profile import get_projects


class PortfolioForecastEngine:


    def __init__(self, future_engine, score_project):
            self.future_engine = future_engine
            self.score_project = score_project

    def simulate_dynamic_portfolio_roadmap(self,night_capacities=None, avg_night_hours=5):
        projects = copy.deepcopy(get_projects())

        simulated = []
        current_night = 1

        while True:
            if night_capacities and current_night > len(night_capacities):
                break

            if current_night > 50:
                print("STOP sécurité roadmap dynamique")
                break

            active_projects = {}

            for name, project in projects.items():
                remaining = project["target_hours"] - project["hours"]

                if remaining > 0:
                    active_projects[name] = project

            if not active_projects:
                break

            best_name = None
            best_score = -9999

            for name, project in active_projects.items():

                future = self.future_engine.estimate(name)
                base_score = self.score_project(project)

                ratio = future.opportunity_ratio

                opportunity_bonus = max(
                    0,
                    min(30, round(30 / max(ratio, 0.1), 1))
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

            if night_capacities:
                capacity = night_capacities[current_night - 1]
                hours_available = capacity.get("hours", avg_night_hours)
            else:
                capacity = None
                hours_available = avg_night_hours

            hours_this_night = min(
                hours_available,
                remaining
            )

            if hours_this_night <= 0:
                current_night += 1
                continue

            project["hours"] += hours_this_night

            simulated.append({
                "night": current_night,
                "date": capacity.get("date") if capacity else None,
                "capacity": hours_available,
                "project": best_name,
                "score": best_score,
                "hours": hours_this_night,
                "target_hours": project["target_hours"],
                "current_hours": project["hours"],
                "remaining_after": max(
                    0,
                    remaining - hours_this_night
                ),
                "completed": remaining - hours_this_night <= 0
            })

            current_night += 1

        return simulated