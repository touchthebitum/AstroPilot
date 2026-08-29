from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from enum import Enum

from astropilot.catalog import CATALOG
from decision.advisor.night_advisor import NightAdvisor
from decision.services.tonight_application_service import TonightResult


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
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


def _clock_text(hour: float) -> str:
    total_minutes = round(hour * 60) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


@dataclass(frozen=True)
class TonightProductivityWindowResponse:
    start_offset_hours: float
    end_offset_hours: float
    start_time: str
    end_time: str
    productivity: float
    productive: bool
    reason: str
    altitude: float
    cloud_cover: float
    moon_penalty: float
    seeing: float


@dataclass(frozen=True)
class TonightProductivityResponse:
    astronomical_hours: float
    productive_hours: float
    confidence: float
    cloud_loss: float
    moon_loss: float
    altitude_loss: float
    weather_loss: float
    display_start_hour: int
    windows: list[TonightProductivityWindowResponse] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class TonightDewRiskResponse:
    level: str
    score: float
    dew_point_c: float
    spread_c: float


@dataclass(frozen=True)
class TonightPostponementRiskResponse:
    level: str
    score: int
    explanations: list[str] = field(default_factory=list)
    required_nights: int | None = None
    productive_hours_per_night: float | None = None
    capacity_source: str | None = None
    historical_nights: int | None = None
    remaining_hours: float | None = None
    favorable_nights: int | None = None
    season_remaining_days: int | None = None


@dataclass(frozen=True)
class TonightSeasonResponse:
    analysis_name: str
    conclusion: str
    confidence: float
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TonightExplanationResponse:
    positives: list[TonightReasonResponse] = field(default_factory=list)
    warnings: list[TonightReasonResponse] = field(default_factory=list)
    information: list[TonightReasonResponse] = field(default_factory=list)
    limiting_factors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TonightTaskResponse:
    start: str
    end: str
    title: str
    description: str = ""
    priority: int = 0


@dataclass(frozen=True)
class TonightAdviceResponse:
    time: str
    priority: str
    category: str
    message: str


@dataclass(frozen=True)
class TonightResponse:
    status: str
    night_date: str | None = None
    target: str | None = None
    catalog_key: str | None = None
    target_common_name: str | None = None
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
    productivity: TonightProductivityResponse | None = None
    dew_risk: TonightDewRiskResponse | None = None
    postponement_risk: TonightPostponementRiskResponse | None = None
    season: TonightSeasonResponse | None = None
    explanation: TonightExplanationResponse | None = None
    reasons: list[TonightReasonResponse] = field(default_factory=list)
    tasks: list[TonightTaskResponse] = field(default_factory=list)
    advices: list[TonightAdviceResponse] = field(default_factory=list)

    @classmethod
    def from_result(cls, result: TonightResult) -> TonightResponse:
        recommendation = result.recommendation
        mission = result.mission
        candidate = (
            recommendation.opportunity.candidate
            if recommendation is not None
            else None
        )
        target = (
            mission.target
            if mission is not None
            else candidate.get("name") if candidate is not None else None
        )
        catalog_key = (
            candidate.get("catalog_key") if candidate is not None else target
        )
        target_common_name = (
            CATALOG.get(catalog_key, {}).get("name")
            if catalog_key is not None
            else None
        )
        if target_common_name == target:
            target_common_name = None

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

        productivity = None
        if mission is not None and mission.productivity is not None:
            source = mission.productivity
            base = source.display_start_hour
            productivity = TonightProductivityResponse(
                astronomical_hours=float(source.astronomical_hours),
                productive_hours=float(source.productive_hours),
                confidence=float(source.confidence),
                cloud_loss=float(source.cloud_loss),
                moon_loss=float(source.moon_loss),
                altitude_loss=float(source.altitude_loss),
                weather_loss=float(source.weather_loss),
                display_start_hour=int(base),
                windows=[
                    TonightProductivityWindowResponse(
                        start_offset_hours=float(window.start_hour),
                        end_offset_hours=float(window.end_hour),
                        start_time=_clock_text(base + window.start_hour),
                        end_time=_clock_text(base + window.end_hour),
                        productivity=float(window.productivity),
                        productive=bool(window.productive),
                        reason=window.reason,
                        altitude=float(window.altitude),
                        cloud_cover=float(window.cloud_cover),
                        moon_penalty=float(window.moon_penalty),
                        seeing=float(window.seeing),
                    )
                    for window in source.windows
                ],
            )

        dew_risk = None
        if mission is not None and mission.dew_risk is not None:
            source = mission.dew_risk
            dew_risk = TonightDewRiskResponse(
                level=source.risk,
                score=float(source.score),
                dew_point_c=float(source.dew_point_c),
                spread_c=float(source.spread_c),
            )

        postponement_risk = None
        if mission is not None and mission.risk_report is not None:
            source = mission.risk_report
            context = source.context
            postponement_risk = TonightPostponementRiskResponse(
                level=source.level,
                score=int(source.score),
                explanations=list(source.explanation),
                required_nights=getattr(context, "required_nights", None),
                productive_hours_per_night=getattr(
                    context,
                    "productive_hours_per_night",
                    None,
                ),
                capacity_source=getattr(
                    context,
                    "night_capacity_source",
                    None,
                ),
                historical_nights=getattr(
                    context,
                    "historical_nights",
                    None,
                ),
                remaining_hours=getattr(context, "remaining_hours", None),
                favorable_nights=getattr(context, "favorable_nights", None),
                season_remaining_days=getattr(
                    context,
                    "season_remaining_days",
                    None,
                ),
            )

        season = None
        if mission is not None and mission.season_analysis is not None:
            source = mission.season_analysis
            season = TonightSeasonResponse(
                analysis_name=source.analysis_name,
                conclusion=source.conclusion,
                confidence=float(source.confidence),
                data=_json_value(source.data),
            )

        reasons = (
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
        )
        explanation = None
        if mission is not None:
            limiting_factors = []
            if (
                mission.astro_quality is not None
                and mission.astro_quality.limiting_factor is not None
            ):
                limiting_factors.append(
                    mission.astro_quality.limiting_factor
                )
            explanation = TonightExplanationResponse(
                positives=[
                    reason for reason in reasons if reason.severity == "success"
                ],
                warnings=[
                    reason for reason in reasons if reason.severity == "warning"
                ],
                information=[
                    reason
                    for reason in reasons
                    if reason.severity not in {"success", "warning"}
                ],
                limiting_factors=limiting_factors,
            )

        tasks = (
            [
                TonightTaskResponse(
                    start=task.start,
                    end=task.end,
                    title=task.title,
                    description=task.description,
                    priority=int(task.priority),
                )
                for task in mission.tasks
            ]
            if mission is not None
            else []
        )
        advices = (
            [
                TonightAdviceResponse(
                    time=advice.time,
                    priority=advice.priority,
                    category=advice.category,
                    message=advice.message,
                )
                for advice in NightAdvisor.build(mission)
            ]
            if mission is not None and mission.productivity is not None
            else []
        )

        return cls(
            status=result.status.value,
            night_date=_text(
                result.night.get("date") if result.night is not None else None
            ),
            target=target,
            catalog_key=catalog_key,
            target_common_name=target_common_name,
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
            productivity=productivity,
            dew_risk=dew_risk,
            postponement_risk=postponement_risk,
            season=season,
            explanation=explanation,
            reasons=reasons,
            tasks=tasks,
            advices=advices,
        )

    def to_dict(self) -> dict:
        return asdict(self)
