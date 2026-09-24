from decision.night_productivity.night_slice import NightSlice
from decision.night_productivity.night_timeline import NightTimeline
from decision.night_productivity.night_conditions_provider import (
    NightConditionsProvider,
)
from decision.night_productivity.productivity_diagnostics import (
    ProductivityLosses,
    SliceProductivityEvaluation,
)


class NightTimelineBuilder:

    @staticmethod
    def _compute_productivity(
        cloud_cover: float,
        moon_penalty: float,
        target_altitude: float,
        humidity: float,
        wind: float,
    ) -> float:
        return NightTimelineBuilder._evaluate_productivity(
            cloud_cover=cloud_cover,
            moon_penalty=moon_penalty,
            target_altitude=target_altitude,
            humidity=humidity,
            wind=wind,
        ).score

    @staticmethod
    def _evaluate_productivity(
        cloud_cover: float,
        moon_penalty: float,
        target_altitude: float,
        humidity: float,
        wind: float,
    ) -> SliceProductivityEvaluation:
        productivity = 1.0

        cloud_loss = cloud_cover / 100 * 0.7
        productivity -= cloud_loss
        moon_loss = moon_penalty * 0.2
        productivity -= moon_loss

        altitude_loss = 0.0
        if target_altitude < 30:
            altitude_loss = 0.25
        elif target_altitude < 50:
            altitude_loss = 0.10
        productivity -= altitude_loss

        humidity_loss = 0.0
        if humidity > 85:
            humidity_loss = 0.15
        productivity -= humidity_loss

        wind_loss = 0.0
        if wind > 20:
            wind_loss = 0.15
        productivity -= wind_loss

        return SliceProductivityEvaluation(
            score=max(0.0, min(1.0, productivity)),
            losses=ProductivityLosses(
                cloud=cloud_loss,
                moon=moon_loss,
                altitude=altitude_loss,
                humidity=humidity_loss,
                wind=wind_loss,
            ),
        )

    @staticmethod
    def build(context):
        timeline, _ = NightTimelineBuilder.build_with_evaluations(context)
        return timeline

    @staticmethod
    def build_with_evaluations(context):
        slices = []
        evaluations = []

        step = 0.25
        current = 0.0

        while current < context.astronomical_hours:

            end = min(current + step, context.astronomical_hours)

            dynamic_cloud = NightConditionsProvider.cloud(current, context)
            dynamic_humidity = NightConditionsProvider.humidity(current, context)
            dynamic_wind = NightConditionsProvider.wind(current, context)
            dynamic_seeing = NightConditionsProvider.seeing(current, context)
            dynamic_altitude = NightConditionsProvider.altitude(current, context)
            dynamic_moon_penalty = NightConditionsProvider.moon_penalty(
                current,
                context,
            )

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

            evaluation = NightTimelineBuilder._evaluate_productivity(
                cloud_cover=dynamic_cloud,
                moon_penalty=dynamic_moon_penalty,
                target_altitude=dynamic_altitude,
                humidity=dynamic_humidity,
                wind=dynamic_wind,
            )

            time_slice.productivity_score = evaluation.score

            slices.append(time_slice)
            evaluations.append(evaluation)

            current = end

        return NightTimeline(slices), tuple(evaluations)
