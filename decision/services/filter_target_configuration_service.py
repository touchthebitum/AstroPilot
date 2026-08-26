from __future__ import annotations

from decision.portfolio.project_filter_targets import (
    ProjectFilterTargets,
)
from dataclasses import dataclass

@dataclass(frozen=True)
class FilterTargetConfiguration:
    project_name: str
    target_hours: float
    filter_targets: dict[str, float]
    configured: bool

class FilterTargetConfigurationService:
    def __init__(
        self,
        *,
        load_profile,
        save_profile,
    ):
        self.load_profile = load_profile
        self.save_profile = save_profile

    def get(
        self,
        *,
        project_name: str,
    ) -> dict[str, float]:
        _, project = self._load_project(
            project_name=project_name,
        )

        return ProjectFilterTargets.get(project)

    def configure(
        self,
        *,
        project_name: str,
        filter_targets: dict[str, float],
    ) -> dict[str, float]:
        profile, project = self._load_project(
            project_name=project_name,
        )

        normalized_targets = {
            filter_type: float(hours)
            for filter_type, hours in filter_targets.items()
        }

        if any(
            hours < 0
            for hours in normalized_targets.values()
        ):
            raise ValueError(
                "filter target hours must be non-negative"
            )

        candidate = dict(project)
        candidate["filter_targets"] = normalized_targets

        ProjectFilterTargets.validate(candidate)

        project["filter_targets"] = normalized_targets

        self.save_profile(profile)

        return ProjectFilterTargets.get(project)

    def _load_project(
        self,
        *,
        project_name: str,
    ) -> tuple[dict, dict]:
        profile = self.load_profile()
        projects = profile.get("projects", {})

        if project_name not in projects:
            raise ValueError(
                f"Unknown project: {project_name}"
            )

        return profile, projects[project_name]

    def describe(
        self,
        *,
        project_name: str,
    ) -> FilterTargetConfiguration:
        _, project = self._load_project(
            project_name=project_name,
        )

        filter_targets = ProjectFilterTargets.get(
            project
        )

        return FilterTargetConfiguration(
            project_name=project_name,
            target_hours=float(
                project.get("target_hours", 0.0)
            ),
            filter_targets=filter_targets,
            configured=bool(filter_targets),
        )

    def clear(
        self,
        *,
        project_name: str,
    ) -> None:
        profile, project = self._load_project(
            project_name=project_name,
        )

        if "filter_targets" not in project:
            return

        del project["filter_targets"]

        self.save_profile(profile)
