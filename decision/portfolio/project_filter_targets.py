from __future__ import annotations


class ProjectFilterTargets:
    @staticmethod
    def get(
        project: dict,
    ) -> dict[str, float]:
        raw_targets = project.get(
            "filter_targets",
            {},
        )

        targets = {}

        for filter_type, hours in raw_targets.items():
            value = max(
                0.0,
                float(hours),
            )

            targets[filter_type] = value

        return targets

    @staticmethod
    def is_consistent(
        project: dict,
        tolerance: float = 0.01,
    ) -> bool:
        targets = ProjectFilterTargets.get(project)

        if not targets:
            return True

        project_target = max(
            0.0,
            float(project.get("target_hours", 0.0)),
        )

        filter_total = ProjectFilterTargets.total_target_hours(
            project
        )

        return (
            abs(filter_total - project_target)
            <= tolerance
        )

    @staticmethod
    def validate(
        project: dict,
    ) -> None:
        if not ProjectFilterTargets.is_consistent(project):
            project_target = float(
                project.get("target_hours", 0.0)
            )

            filter_total = (
                ProjectFilterTargets.total_target_hours(
                    project
                )
            )

            raise ValueError(
                "filter_targets total "
                f"({filter_total:.2f} h) "
                "must match target_hours "
                f"({project_target:.2f} h)"
            )

    @staticmethod
    def total_target_hours(
        project: dict,
    ) -> float:
        targets = ProjectFilterTargets.get(
            project,
        )

        return round(
            sum(targets.values()),
            2,
        )
