from decision.night_productivity.night_slice import NightSlice
from decision.night_productivity.night_timeline import NightTimeline
from decision.night_productivity.night_conditions_provider import NightConditionsProvider


class NightTimelineBuilder:

    @staticmethod
    def _compute_productivity(
        cloud_cover: float,
        moon_penalty: float,
        target_altitude: float,
        humidity: float,
        wind: float,
    ) -> float:
        productivity = 1.0

        productivity -= cloud_cover / 100 * 0.7
        productivity -= moon_penalty * 0.2

        if target_altitude < 30:
            productivity -= 0.25
        elif target_altitude < 50:
            productivity -= 0.10

        if humidity > 85:
            productivity -= 0.15

        if wind > 20:
            productivity -= 0.15

        return max(0.0, min(1.0, productivity))


    def build(context):

        slices = []

        step = 0.25
        current = 0.0

        while current < context.astronomical_hours:

            end = min(current + step, context.astronomical_hours)

            dynamic_cloud = NightConditionsProvider.cloud(current, context)
            dynamic_humidity = NightConditionsProvider.humidity(current, context)
            dynamic_wind = NightConditionsProvider.wind(current, context)
            dynamic_seeing = NightConditionsProvider.seeing(current, context)
            dynamic_altitude = NightConditionsProvider.altitude(current, context)
            dynamic_moon_penalty = NightConditionsProvider.moon_penalty(current,context)

            time_slice = NightSlice(
                start_hour=current,
                end_hour=end,

                target_altitude=dynamic_altitude,
                target_azimuth=0.0,

                moon_altitude=0.0,
                moon_separation=0.0,
                moon_penalty=dynamic_moon_penalty,

                cloud_cover=dynamic_cloud,
                humidity=dynamic_humidity,
                wind=dynamic_wind,
                seeing=dynamic_seeing,
                sqm=0.0,

                astro_score=0.0,
                conditions_score=0.0,
                productivity_score=0.0,
            )

            productivity = NightTimelineBuilder._compute_productivity(
            cloud_cover=dynamic_cloud,
            moon_penalty=dynamic_moon_penalty,
            target_altitude=dynamic_altitude,
            humidity=dynamic_humidity,
            wind=dynamic_wind,
            )

            time_slice.productivity_score = productivity

            slices.append(time_slice)

            current = end


        return NightTimeline(slices)
