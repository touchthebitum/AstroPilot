from decision.filtering.selected_filter import SelectedFilter


class FilterSelectionEngine:
    @staticmethod
    def select(context) -> SelectedFilter | None:
        available = list(context.available_filters)

        if not available:
            return None

        preferred = []

        if (
            context.target_type == "nebula"
            and context.target_subtype == "emission"
        ):
            preferred = ["Ha", "OIII", "SII"]

        elif context.target_type == "supernova_remnant":
            preferred = ["OIII", "Ha", "SII"]

        elif context.target_type in ("galaxy", "cluster"):
            preferred = ["LRGB"]

        if context.moon_penalty >= 0.6:
            moon_safe = ["Ha", "SII", "OIII"]

            preferred = [
                filter_type
                for filter_type in moon_safe
                if filter_type in preferred
            ] + [
                filter_type
                for filter_type in preferred
                if filter_type not in moon_safe
            ]

        candidates = [
            available_filter
            for filter_type in preferred
            for available_filter in available
            if available_filter.filter_type == filter_type
        ]

        if candidates:
            remaining = context.remaining_hours_by_filter

            if remaining:
                unfinished = [
                    candidate
                    for candidate in candidates
                    if remaining.get(
                        candidate.filter_type,
                        0.0,
                    ) > 0
                ]

                if unfinished:
                    if context.moon_penalty >= 0.6:
                        return unfinished[0]

                    return max(
                        unfinished,
                        key=lambda item: remaining.get(
                            item.filter_type,
                            0.0,
                        ),
                    )

            return candidates[0]

        return available[0]
