from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.validation.weather_window_coverage import (
    WeatherWindowCoverageError,
    validate_selected_window_weather_coverage,
)
from decision.weather.provider_reliability import WeatherLocation
from decision.weather.weather_ingress import WeatherFreshness, WeatherSnapshot
from decision.weather.weather_trust_decision import (
    WeatherDecisionContext,
    WeatherTrustDecision,
    WeatherTrustDecisionEvaluator,
    WeatherTrustEvidence,
)


_WINDOW_COVERAGE_ISSUES = {
    "window_starts_before_weather",
    "window_ends_after_weather",
}


@dataclass(frozen=True)
class CandidateAssessment:
    productive_window: ProductiveWindowAssessment
    weather_decision: WeatherTrustDecision

    @classmethod
    def build(
        cls,
        *,
        candidate,
        object_evaluations: Mapping[str, Mapping[str, Any]],
        profile: Mapping[str, Any],
        weather_snapshot: WeatherSnapshot,
        weather_freshness: WeatherFreshness | None,
        decision_location: WeatherLocation,
        build_mission_input: Callable[..., Any],
    ) -> CandidateAssessment:
        evaluation = object_evaluations[candidate.catalog_key]
        mission_input = build_mission_input(evaluation, profile=profile)
        productive_window = ProductiveWindowAssessment.build(
            target=candidate.catalog_key,
            context=evaluation["decision_context"],
            mission_input=mission_input,
        )

        selected_window_covered = True
        try:
            validate_selected_window_weather_coverage(
                productive_window,
                weather_snapshot,
            )
        except WeatherWindowCoverageError as exc:
            issues = set(exc.issues)
            if issues and issues <= _WINDOW_COVERAGE_ISSUES:
                selected_window_covered = False
            else:
                raise

        weather_decision = WeatherTrustDecisionEvaluator.evaluate(
            WeatherTrustEvidence(
                snapshot=weather_snapshot,
                freshness=weather_freshness,
                selected_window_covered=selected_window_covered,
                provider_reliability=None,
            ),
            context=WeatherDecisionContext(
                provider_id=weather_snapshot.provider,
                decision_location=decision_location,
                reliability_context=None,
            ),
        )
        return cls(
            productive_window=productive_window,
            weather_decision=weather_decision,
        )
