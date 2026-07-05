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
                altitude=NightConditionsProvider.altitude(current, context),
                cloud_cover=NightConditionsProvider.cloud(current, context),
                humidity=NightConditionsProvider.humidity(current, context),
                wind=NightConditionsProvider.wind(current, context),
                seeing=NightConditionsProvider.seeing(current, context),
                moon_penalty=NightConditionsProvider.moon_penalty(current, context),
            )

            productivity = NightSliceEvaluator.evaluate(time_slice)

            time_slice.productivity = productivity

            slices.append(time_slice)
                        

            current = end

        return NightTimeline(slices)
