from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from decision.services.tonight_application_service import TonightResult


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


@dataclass(frozen=True)
class TonightReasonResponse:
    title: str
    severity: str
    value: str | None = None


@dataclass(frozen=True)
class TonightFilterResponse:
    name: str
    filter_type: str
    bandwidth_nm: float | None = None


@dataclass(frozen=True)
class TonightAstroQualityResponse:
    score: float
    confidence: float
    label: str
    limiting_factor: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)


def _quality_label(score: float) -> str:
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "very_good"
    if score >= 60:
        return "good"
    if score >= 40:
        return "average"
    return "low"


@dataclass(frozen=True)
class TonightResponse:
    status: str
    night_date: str | None = None
    target: str | None = None
    catalog_key: str | None = None
    action: str | None = None
    recommendation_confidence: float | None = None
    mission_confidence: float | str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    window_start: str | None = None
    window_end: str | None = None
    recommended_hours: float = 0.0
    expected_gain: float = 0.0
    equipment: list[str] = field(default_factory=list)
    selected_filter: TonightFilterResponse | None = None
    astro_quality: TonightAstroQualityResponse | None = None
    reasons: list[TonightReasonResponse] = field(default_factory=list)

    @classmethod
    def from_result(cls, result: TonightResult) -> TonightResponse:
        recommendation = result.recommendation
        mission = result.mission
        candidate = (
            recommendation.opportunity.candidate
            if recommendation is not None
            else None
        )

        scores = {}
        if candidate is not None:
            for name in (
                "astro_score",
                "decision_score",
                "final_score",
                "portfolio_score",
                "global_score",
                "setup_score",
            ):
                value = candidate.get(name)
                if value is not None:
                    scores[name] = float(value)

        selected_filter = None
        if mission is not None and mission.selected_filter is not None:
            selected_filter = TonightFilterResponse(
                name=mission.selected_filter.name,
                filter_type=mission.selected_filter.filter_type,
                bandwidth_nm=mission.selected_filter.bandwidth_nm,
            )

        astro_quality = None
        if mission is not None and mission.astro_quality is not None:
            quality = mission.astro_quality
            astro_quality = TonightAstroQualityResponse(
                score=float(quality.score),
                confidence=float(quality.confidence),
                label=_quality_label(quality.score),
                limiting_factor=quality.limiting_factor,
                metrics={
                    name: float(value)
                    for name, value in quality.metrics.items()
                },
            )

        return cls(
            status=result.status.value,
            night_date=_text(
                result.night.get("date") if result.night is not None else None
            ),
            target=(
                mission.target
                if mission is not None
                else candidate.get("name") if candidate is not None else None
            ),
            catalog_key=(
                candidate.get("catalog_key") if candidate is not None else None
            ),
            action=(
                recommendation.opportunity.action.value
                if recommendation is not None
                else None
            ),
            recommendation_confidence=(
                float(recommendation.confidence)
                if recommendation is not None
                else None
            ),
            mission_confidence=(
                mission.confidence if mission is not None else None
            ),
            scores=scores,
            window_start=_text(
                mission.window_start if mission is not None else None
            ),
            window_end=_text(
                mission.window_end if mission is not None else None
            ),
            recommended_hours=(
                float(mission.recommended_hours) if mission is not None else 0.0
            ),
            expected_gain=(
                float(mission.expected_gain) if mission is not None else 0.0
            ),
            equipment=list(mission.equipment) if mission is not None else [],
            selected_filter=selected_filter,
            astro_quality=astro_quality,
            reasons=(
                [
                    TonightReasonResponse(
                        title=reason.title,
                        severity=reason.severity,
                        value=reason.value,
                    )
                    for reason in mission.reasons
                ]
                if mission is not None
                else []
            ),
        )

    def to_dict(self) -> dict:
        return asdict(self)
