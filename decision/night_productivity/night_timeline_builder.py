from decision.night_productivity.night_slice import NightSlice
from decision.night_productivity.night_timeline import NightTimeline
from decision.night_productivity.night_slice_evaluator import NightSliceEvaluator
from decision.night_productivity.night_conditions_provider import NightConditionsProvider


class NightTimelineBuilder:

    @staticmethod
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

            time_slice = NightSlice(
                start_hour=current,
                end_hour=end,

                target_altitude=dynamic_altitude,
                target_azimuth=0.0,

                moon_altitude=0.0,
                moon_separation=0.0,

                cloud_cover=dynamic_cloud,
                humidity=dynamic_humidity,
                wind=dynamic_wind,
                seeing=dynamic_seeing,
                sqm=0.0,

                astro_score=0.0,
                conditions_score=0.0,
                productivity_score=0.0,
            )

            productivity = NightSliceEvaluator.evaluate(time_slice)
            time_slice.productivity_score = productivity

            slices.append(time_slice)

            current = end


        return NightTimeline(slices)
