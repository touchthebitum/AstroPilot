from decision.night_productivity.night_productivity_context import (
    NightProductivityContext,
)

from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)

from decision.night_productivity.night_window_builder import NightWindowBuilder

from decision.night_productivity.night_timeline_builder import NightTimelineBuilder

class NightProductivityEngine:

    @staticmethod
    def evaluate(
        context: NightProductivityContext,
    ):
        timeline = NightTimelineBuilder.build(context)
        cloud_loss = context.astronomical_hours * (context.cloud_cover / 100) * 0.7
        moon_loss = context.astronomical_hours * context.moon_penalty * 0.3

        altitude_loss = 0
        if context.altitude_score < 5:
            altitude_loss = context.astronomical_hours * 0.25
        elif context.altitude_score < 7:
            altitude_loss = context.astronomical_hours * 0.10

        weather_loss = 0
        if context.humidity > 85:
            weather_loss += context.astronomical_hours * 0.15
        if context.wind > 20:
            weather_loss += context.astronomical_hours * 0.15

        total_loss = cloud_loss + moon_loss + altitude_loss + weather_loss

        productive_hours = sum(
            (s.end_hour - s.start_hour) * s.productivity_score
            for s in timeline.slices
        )

        confidence = (
            productive_hours / context.astronomical_hours
            if context.astronomical_hours > 0
            else 0
        )

        return NightProductivityResult(
            astronomical_hours=context.astronomical_hours,
            productive_hours=round(productive_hours, 2),
            confidence=round(confidence, 2),
            cloud_loss=round(cloud_loss, 2),
            moon_loss=round(moon_loss, 2),
            altitude_loss=round(altitude_loss, 2),
            weather_loss=round(weather_loss, 2),
            windows=NightWindowBuilder.build(context),
            display_start_hour=getattr(context, "display_start_hour", 22),
            timeline=timeline,
        )

