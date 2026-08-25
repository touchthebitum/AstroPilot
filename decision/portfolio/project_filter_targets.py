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