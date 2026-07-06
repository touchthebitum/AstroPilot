from decision.night_productivity.night_window import NightWindow
from decision.night_productivity.night_conditions_provider import NightConditionsProvider


class NightWindowBuilder:

    @staticmethod
    def build(context):
        windows = []
        step = 0.25
        current = 0.0

        while current < context.astronomical_hours:
            end = min(current + step, context.astronomical_hours)

            night_progress = current / context.astronomical_hours if context.astronomical_hours else 0

            dynamic_altitude = NightConditionsProvider.altitude(current, context)
            dynamic_cloud = NightConditionsProvider.cloud(current, context)
            dynamic_moon = NightConditionsProvider.moon_penalty(current, context)

            productivity = 1.0
            productivity -= dynamic_cloud / 100 * 0.7
            productivity -= dynamic_moon * 0.2

            if dynamic_altitude < 5:
                productivity -= 0.25
            elif dynamic_altitude < 7:
                productivity -= 0.10

            if context.humidity > 85:
                productivity -= 0.15

            if context.wind > 20:
                productivity -= 0.15

            productivity = max(0.0, min(1.0, productivity))


            windows.append(
                NightWindow(
                    start_hour=current,
                    end_hour=end,
                    productivity=productivity,
                    altitude=round(dynamic_altitude, 2),
                    cloud_cover=round(dynamic_cloud, 1),
                    moon_penalty=round(dynamic_moon, 2),
                    seeing=context.seeing,
                    productive=productivity >= 0.7,
                    reason="Créneau exploitable" if productivity >= 0.7 else "Créneau dégradé",
                )
            )

            current = end

        return windows