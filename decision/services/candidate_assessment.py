from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import SessionAvailability
from decision.services.session_availability_windowing import (
    select_duration_availability_window,
)
from decision.validation.weather_window_coverage import (
    WeatherWindowCoverageError,
    validate_selected_window_weather_coverage,
)
from decision.validation.decision_consistency import DecisionConsistencyGate
from decision.weather.provider_reliability import WeatherLocation
from decision.weather.weather_ingress import WeatherFreshness, WeatherSnapshot
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
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


class CandidateViabilityEvaluator:
    @staticmethod
    def is_viable(assessment: CandidateAssessment | None) -> bool:
        if assessment is None:
            return False

        DecisionConsistencyGate.validate_mission(
            assessment.productive_window
        )
        return (
            DecisionConsistencyGate.has_productive_window(
                assessment.productive_window
            )
            and assessment.weather_decision.admissibility
            in {
                WeatherDecisionAdmissibility.ADMISSIBLE,
                WeatherDecisionAdmissibility.CAUTION,
            }
        )


def select_viable_alternatives(
    shortlist_entries: Iterable[Any],
    viable_catalog_keys: Collection[str],
    *,
    primary_catalog_key: str | None,
) -> tuple[Any, ...]:
    alternatives = []
    for candidate in shortlist_entries:
        if candidate.catalog_key == primary_catalog_key:
            continue
        if candidate.catalog_key not in viable_catalog_keys:
            continue
        alternatives.append(candidate)
        if len(alternatives) == 2:
            break
    return tuple(alternatives)


def select_actionable_alternatives(
    shortlist_entries: Iterable[Any],
    viable_catalog_keys: Collection[str],
    candidate_assessments: Mapping[str, CandidateAssessment],
    availability: SessionAvailability | None,
    *,
    primary_catalog_key: str | None,
) -> tuple[Any, ...]:
    """Expose physically viable alternatives with a usable session window."""
    if availability is None:
        return select_viable_alternatives(
            shortlist_entries,
            viable_catalog_keys,
            primary_catalog_key=primary_catalog_key,
        )
    if not isinstance(availability, SessionAvailability):
        raise TypeError("Expected SessionAvailability or None")

    alternatives = []
    for candidate in shortlist_entries:
        if candidate.catalog_key == primary_catalog_key:
            continue
        if candidate.catalog_key not in viable_catalog_keys:
            continue
        assessment = candidate_assessments.get(candidate.catalog_key)
        if assessment is None:
            continue
        actionable_window = select_duration_availability_window(
            assessment.productive_window,
            availability,
        )
        if actionable_window is None:
            continue
        alternatives.append(candidate)
        if len(alternatives) == 2:
            break
    return tuple(alternatives)
