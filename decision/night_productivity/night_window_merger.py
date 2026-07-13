from decision.night_productivity.night_window import NightWindow


class NightWindowMerger:
    DEFAULT_THRESHOLD = 0.70

    @staticmethod
    def merge(timeline, threshold: float = DEFAULT_THRESHOLD) -> list[NightWindow]:
        merged_windows: list[NightWindow] = []
        current_slices = []

        for night_slice in timeline.slices:
            if night_slice.productivity_score >= threshold:
                current_slices.append(night_slice)
            elif current_slices:
                merged_windows.append(
                    NightWindowMerger._build_window(current_slices, threshold)
                )
                current_slices = []

        # Ferme la dernière fenêtre si la nuit se termine
        # pendant une séquence productive.
        if current_slices:
            merged_windows.append(
                NightWindowMerger._build_window(current_slices, threshold)
            )

        return merged_windows

    @staticmethod
    def _build_window(slices, threshold: float) -> NightWindow:
        count = len(slices)

        productivity = sum(
            night_slice.productivity_score
            for night_slice in slices
        ) / count

        altitude = sum(
            night_slice.target_altitude
            for night_slice in slices
        ) / count

        cloud_cover = sum(
            night_slice.cloud_cover
            for night_slice in slices
        ) / count

        moon_penalty = sum(
            night_slice.moon_penalty
            for night_slice in slices
        ) / count

        seeing = sum(
            night_slice.seeing
            for night_slice in slices
        ) / count

        return NightWindow(
            start_hour=slices[0].start_hour,
            end_hour=slices[-1].end_hour,
            productivity=round(productivity, 3),
            altitude=round(altitude, 2),
            cloud_cover=round(cloud_cover, 1),
            moon_penalty=round(moon_penalty, 2),
            seeing=round(seeing, 2),
            productive=productivity >= threshold,
            reason="Fenêtre productive fusionnée",
        )
