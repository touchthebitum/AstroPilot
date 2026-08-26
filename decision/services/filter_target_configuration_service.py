from __future__ import annotations

from decision.portfolio.project_filter_targets import (
    ProjectFilterTargets,
)


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
        profile = self.load_profile()
        projects = profile.get("projects", {})

        if project_name not in projects:
            raise ValueError(
                f"Unknown project: {project_name}"
            )

        return ProjectFilterTargets.get(
            projects[project_name]
        )

    def configure(
        self,
        *,
        project_name: str,
        filter_targets: dict[str, float],
    ) -> dict[str, float]:
        profile = self.load_profile()
        projects = profile.get("projects", {})

        if project_name not in projects:
            raise ValueError(
                f"Unknown project: {project_name}"
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

        project = dict(projects[project_name])
        project["filter_targets"] = normalized_targets

        ProjectFilterTargets.validate(project)

        projects[project_name]["filter_targets"] = (
            normalized_targets
        )

        self.save_profile(profile)

        return ProjectFilterTargets.get(
            projects[project_name]
        )

    def clear(
        self,
        *,
        project_name: str,
    ) -> None:
        profile = self.load_profile()
        projects = profile.get("projects", {})

        if project_name not in projects:
            raise ValueError(
                f"Unknown project: {project_name}"
            )

        project = projects[project_name]

        if "filter_targets" not in project:
            return

        del project["filter_targets"]

        self.save_profile(profile)