from __future__ import annotations

from dataclasses import dataclass
from decision.portfolio.project_filter_targets import (
    ProjectFilterTargets,
)

@dataclass(frozen=True)
class FilterProgress:
    filter_type: str
    acquired_hours: float
    target_hours: float
    remaining_hours: float
    progress: float


class ProjectFilterProgress:
    @staticmethod
    def acquired_hours(
        *,
        project_name: str,
        filter_type: str,
        sessions: list[dict],
    ) -> float:
        total = 0.0

        for session in sessions:
            if session.get("object") != project_name:
                continue

            if session.get("filter_type") != filter_type:
                continue

            total += float(
                session.get("hours", 0.0)
            )

        return round(total, 2)


    @staticmethod
    def evaluate_project(
        *,
        project_name: str,
        project: dict,
        sessions: list[dict],
    ) -> dict[str, FilterProgress]:
        ProjectFilterTargets.validate(project)
        targets = ProjectFilterTargets.get(project)

        return {
            filter_type: ProjectFilterProgress.evaluate(
                project_name=project_name,
                filter_type=filter_type,
                target_hours=target_hours,
                sessions=sessions,
            )
            for filter_type, target_hours in targets.items()
        }

    @staticmethod
    def evaluate(
        *,
        project_name: str,
        filter_type: str,
        target_hours: float,
        sessions: list[dict],
    ) -> FilterProgress:
        acquired = ProjectFilterProgress.acquired_hours(
            project_name=project_name,
            filter_type=filter_type,
            sessions=sessions,
        )

        target = max(
            0.0,
            float(target_hours),
        )

        if target <= 0:
            remaining = 0.0
            progress = 0.0
        else:
            remaining = max(
                0.0,
                target - acquired,
            )

            progress = min(
                100.0,
                acquired / target * 100.0,
            )

        return FilterProgress(
            filter_type=filter_type,
            acquired_hours=round(acquired, 2),
            target_hours=round(target, 2),
            remaining_hours=round(remaining, 2),
            progress=round(progress, 1),
        )
