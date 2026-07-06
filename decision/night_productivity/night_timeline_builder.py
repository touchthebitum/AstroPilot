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
            time_slice = NightSlice(
                        start_hour=current,
                        end_hour=end,

                        target_altitude=0.0,
                        target_azimuth=0.0,

                        moon_altitude=0.0,
                        moon_separation=0.0,

                        cloud_cover=0.0,
                        humidity=0.0,
                        wind=0.0,
                        seeing=0.0,
                        sqm=0.0,

                        astro_score=0.0,
                        conditions_score=0.0,
                        productivity_score=0.0,
                    )

            productivity = NightSliceEvaluator.evaluate(time_slice)

            time_slice.productivity = productivity

            slices.append(time_slice)
                        

            current = end

        return NightTimeline(slices)
