from decision.night_productivity.night_window import NightWindow

class NightWindowBuilder:

    @staticmethod
    def build(context, timeline):
        windows = []
        for slice in timeline.slices:
            windows.append(
                NightWindow(
                    start_hour=slice.start_hour,
                    end_hour=slice.end_hour,
                    productivity=slice.productivity_score,
                    altitude=round(slice.target_altitude, 2),
                    cloud_cover=round(slice.cloud_cover, 1),
                    moon_penalty=round(getattr(slice, "moon_penalty", 0.0), 2),
                    seeing=slice.seeing,
                    productive=slice.productivity_score >= 0.7,
                    reason=(
                        "Créneau exploitable"
                        if slice.productivity_score >= 0.7
                        else "Créneau dégradé"
                    ),
                )
            )
            

        return windows