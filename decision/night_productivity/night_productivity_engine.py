from dataclasses import dataclass
from datetime import timedelta, timezone

from decision.night_productivity.night_productivity_context import (
    NightProductivityContext,
)

from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)

from decision.night_productivity.night_window_merger import NightWindowMerger

from decision.night_productivity.night_timeline_builder import NightTimelineBuilder
from decision.night_productivity.productivity_diagnostics import (
    PRODUCTIVE_SLICE_THRESHOLD,
    ProductivityBreakdown,
)


@dataclass(frozen=True, slots=True)
class NightProductivityEvaluation:
    result: NightProductivityResult
    breakdown: ProductivityBreakdown | None


class NightProductivityEngine:

    @staticmethod
    def evaluate(
        context: NightProductivityContext,
    ):
        return NightProductivityEngine._evaluate_with_breakdown(context).result

    @staticmethod
    def evaluate_with_breakdown(
        context: NightProductivityContext,
    ) -> NightProductivityEvaluation:
        evaluator = NightProductivityEngine.evaluate
        if not getattr(evaluator, "_provides_productivity_breakdown", False):
            return NightProductivityEvaluation(
                result=evaluator(context),
                breakdown=None,
            )
        return NightProductivityEngine._evaluate_with_breakdown(context)

    @staticmethod
    def _evaluate_with_breakdown(
        context: NightProductivityContext,
    ) -> NightProductivityEvaluation:
        timeline, slice_evaluations = (
            NightTimelineBuilder.build_with_evaluations(context)
        )
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

        result = NightProductivityResult(
            astronomical_hours=context.astronomical_hours,
            productive_hours=round(productive_hours, 2),
            confidence=round(confidence, 2),
            cloud_loss=round(cloud_loss, 2),
            moon_loss=round(moon_loss, 2),
            altitude_loss=round(altitude_loss, 2),
            weather_loss=round(weather_loss, 2),
            windows=NightWindowMerger.merge(timeline),
            display_start_hour=getattr(context, "display_start_hour", 22),
            timeline=timeline,
        )
        observation_time = getattr(context, "observation_time", None)
        breakdown = None
        if (
            slice_evaluations
            and observation_time is not None
            and observation_time.tzinfo is not None
            and observation_time.utcoffset() is not None
        ):
            best_score = max(item.score for item in slice_evaluations)
            best_index = next(
                index
                for index, item in enumerate(slice_evaluations)
                if item.score == best_score
            )
            best_slice = timeline.slices[best_index]
            observation_time_utc = observation_time.astimezone(timezone.utc)
            breakdown = ProductivityBreakdown(
                evaluated_slice_count=len(slice_evaluations),
                productive_slice_count=sum(
                    item.score >= PRODUCTIVE_SLICE_THRESHOLD
                    for item in slice_evaluations
                ),
                best_slice_start=(
                    observation_time_utc
                    + timedelta(hours=best_slice.start_hour)
                ).astimezone(observation_time.tzinfo),
                best_slice_end=(
                    observation_time_utc
                    + timedelta(hours=best_slice.end_hour)
                ).astimezone(observation_time.tzinfo),
                best_slice_score=best_score,
                best_slice_tie_count=sum(
                    item.score == best_score for item in slice_evaluations
                ),
                productive_slice_threshold=PRODUCTIVE_SLICE_THRESHOLD,
                losses=slice_evaluations[best_index].losses,
            )
        return NightProductivityEvaluation(result=result, breakdown=breakdown)


NightProductivityEngine.evaluate._provides_productivity_breakdown = True
