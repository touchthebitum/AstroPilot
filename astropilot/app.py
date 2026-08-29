from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from decision.services.tonight_application_service import TonightStatus
from decision.services.tonight_response import TonightResponse
from decision.weather.weather_ingress import (
    WeatherFreshness,
    WeatherIngressError,
    WeatherSnapshot,
    validate_weather_freshness,
)
from decision.validation.decision_consistency import DecisionConsistencyError
from decision.validation.weather_window_coverage import (
    WeatherWindowCoverageError,
    validate_selected_window_weather_coverage,
)
from decision.location.location_time import LocationTimeError


class LocationRequest(BaseModel):
    name: str = "Buttes"
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class TonightRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "location": {
                        "name": "Buttes",
                        "latitude": 46.7508,
                        "longitude": 6.5495,
                    },
                    "profile": {},
                    "equipment": "widefield",
                    "goal": "balanced",
                    "target": "deep_sky",
                    "bortle": 3,
                }
            ]
        }
    )

    location: LocationRequest | None = None
    profile: dict = Field(default_factory=dict)
    equipment: str | None = None
    goal: Literal[
        "balanced",
        "galaxies",
        "nebulae",
        "widefield",
        "small_targets",
        "highest_score",
        "best_setup",
    ] = "balanced"
    target: Literal[
        "milky_way",
        "deep_sky",
        "planetary",
        "moon",
        "nightscape",
    ] = "deep_sky"
    bortle: int = Field(default=3, ge=1, le=9)


class TonightReasonModel(BaseModel):
    title: str
    severity: str
    value: str | None = None


class TonightFilterModel(BaseModel):
    name: str
    filter_type: str
    bandwidth_nm: float | None = None


class TonightAstroQualityModel(BaseModel):
    score: float
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Completeness of AQI inputs; not weather forecast reliability."
        ),
    )
    label: str
    limiting_factor: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class TonightProductivityWindowModel(BaseModel):
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


class TonightProductivityModel(BaseModel):
    astronomical_hours: float
    productive_hours: float
    productive_fraction: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Deprecated compatibility alias for productive_fraction; "
            "this is not forecast confidence."
        ),
    )
    cloud_loss: float
    moon_loss: float
    altitude_loss: float
    weather_loss: float
    display_start_hour: int
    windows: list[TonightProductivityWindowModel] = Field(default_factory=list)


class TonightDewRiskModel(BaseModel):
    level: str
    score: float
    dew_point_c: float
    spread_c: float


class TonightPostponementRiskModel(BaseModel):
    level: str
    score: int
    explanations: list[str] = Field(default_factory=list)
    required_nights: int | None = None
    productive_hours_per_night: float | None = None
    capacity_source: str | None = None
    historical_nights: int | None = None
    remaining_hours: float | None = None
    favorable_nights: int | None = None
    season_remaining_days: int | None = None


class TonightSeasonModel(BaseModel):
    analysis_name: str
    conclusion: str
    confidence: float
    data: dict = Field(default_factory=dict)


class TonightExplanationModel(BaseModel):
    positives: list[TonightReasonModel] = Field(default_factory=list)
    warnings: list[TonightReasonModel] = Field(default_factory=list)
    information: list[TonightReasonModel] = Field(default_factory=list)
    limiting_factors: list[str] = Field(default_factory=list)


class TonightTaskModel(BaseModel):
    start: str
    end: str
    title: str
    description: str = ""
    priority: int = 0


class TonightAdviceModel(BaseModel):
    time: str
    priority: str
    category: str
    message: str


class TonightWeatherTrustModel(BaseModel):
    provider: str
    retrieved_at_utc: str
    requested_latitude: float
    requested_longitude: float
    grid_latitude: float
    grid_longitude: float
    grid_distance_km: float
    elevation_m: float | None = None
    timezone: str
    timezone_source: Literal["coordinates_local"]
    utc_offset_seconds: int
    valid_from: str
    valid_until: str
    hour_count: int = Field(ge=24)
    completeness: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["validated"]
    snapshot_age_minutes: float = Field(ge=0.0)
    freshness_status: Literal["fresh"]
    maximum_age_minutes: int = Field(gt=0)


class TonightResponseModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "available",
                    "night_date": "2026-08-29",
                    "target": "NGC 7000",
                    "catalog_key": "ngc7000",
                    "target_common_name": "North America Nebula",
                    "action": "continue_project",
                    "recommendation_confidence": 0.91,
                    "mission_confidence": 0.88,
                    "scores": {"astronomy": 84.0, "mission": 89.0},
                    "window_start": "22:30",
                    "window_end": "02:30",
                    "recommended_hours": 4.0,
                    "expected_gain": 3.4,
                    "equipment": ["widefield", "dual_narrowband"],
                    "selected_filter": {
                        "name": "L-eXtreme",
                        "filter_type": "dual_narrowband",
                        "bandwidth_nm": 7.0,
                    },
                    "astro_quality": {
                        "score": 86.0,
                        "confidence": 0.9,
                        "label": "very_good",
                        "limiting_factor": "moon",
                        "metrics": {"altitude": 92.0, "moon": 71.0},
                    },
                    "productivity": {
                        "astronomical_hours": 6.2,
                        "productive_hours": 4.0,
                        "productive_fraction": 0.65,
                        "confidence": 0.65,
                        "cloud_loss": 0.8,
                        "moon_loss": 0.7,
                        "altitude_loss": 0.4,
                        "weather_loss": 0.3,
                        "display_start_hour": 20,
                        "windows": [
                            {
                                "start_offset_hours": 2.5,
                                "end_offset_hours": 6.5,
                                "start_time": "22:30",
                                "end_time": "02:30",
                                "productivity": 0.85,
                                "productive": True,
                                "reason": "Strong altitude and clear sky",
                                "altitude": 62.0,
                                "cloud_cover": 12.0,
                                "moon_penalty": 0.18,
                                "seeing": 1.7,
                            }
                        ],
                    },
                    "dew_risk": {
                        "level": "low",
                        "score": 18.0,
                        "dew_point_c": 7.0,
                        "spread_c": 5.0,
                    },
                    "postponement_risk": {
                        "level": "medium",
                        "score": 44,
                        "explanations": ["Five favorable nights remain."],
                        "required_nights": 2,
                        "productive_hours_per_night": 3.5,
                        "capacity_source": "forecast",
                        "historical_nights": 8,
                        "remaining_hours": 6.0,
                        "favorable_nights": 5,
                        "season_remaining_days": 24,
                    },
                    "season": {
                        "analysis_name": "season_window",
                        "conclusion": "The target remains well placed.",
                        "confidence": 0.82,
                        "data": {"remaining_days": 24},
                    },
                    "explanation": {
                        "positives": [
                            {
                                "title": "High altitude",
                                "severity": "positive",
                                "value": "62 deg",
                            }
                        ],
                        "warnings": [],
                        "information": [],
                        "limiting_factors": ["moon"],
                    },
                    "reasons": [
                        {
                            "title": "Portfolio priority",
                            "severity": "positive",
                            "value": "high",
                        }
                    ],
                    "tasks": [
                        {
                            "start": "T-30 min",
                            "end": "T-20 min",
                            "title": "Installer le matériel",
                            "description": "",
                            "priority": 0,
                        }
                    ],
                    "advices": [
                        {
                            "time": "Avant installation",
                            "priority": "MEDIUM",
                            "category": "weather",
                            "message": "Check the latest weather forecast.",
                        }
                    ],
                    "weather_trust": {
                        "provider": "Open-Meteo",
                        "retrieved_at_utc": "2026-08-29T18:00:00+00:00",
                        "requested_latitude": 46.7508,
                        "requested_longitude": 6.5495,
                        "grid_latitude": 46.75,
                        "grid_longitude": 6.55,
                        "grid_distance_km": 0.1,
                        "elevation_m": 837.0,
                        "timezone": "Europe/Zurich",
                        "timezone_source": "coordinates_local",
                        "utc_offset_seconds": 7200,
                        "valid_from": "2026-08-29T00:00:00+02:00",
                        "valid_until": "2026-09-04T23:00:00+02:00",
                        "hour_count": 168,
                        "completeness": 1.0,
                        "validation_status": "validated",
                        "snapshot_age_minutes": 4.5,
                        "freshness_status": "fresh",
                        "maximum_age_minutes": 90,
                    },
                }
            ]
        }
    )

    status: str
    night_date: str | None = None
    target: str | None = None
    catalog_key: str | None = None
    target_common_name: str | None = None
    action: str | None = None
    recommendation_confidence: float | None = None
    mission_confidence: float | str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    window_start: str | None = None
    window_end: str | None = None
    recommended_hours: float = 0.0
    expected_gain: float = 0.0
    equipment: list[str] = Field(default_factory=list)
    selected_filter: TonightFilterModel | None = None
    astro_quality: TonightAstroQualityModel | None = None
    productivity: TonightProductivityModel | None = None
    dew_risk: TonightDewRiskModel | None = None
    postponement_risk: TonightPostponementRiskModel | None = None
    season: TonightSeasonModel | None = None
    explanation: TonightExplanationModel | None = None
    reasons: list[TonightReasonModel] = Field(default_factory=list)
    tasks: list[TonightTaskModel] = Field(default_factory=list)
    advices: list[TonightAdviceModel] = Field(default_factory=list)
    weather_trust: TonightWeatherTrustModel | None = None


def _production_service_factory():
    from astro_score import build_tonight_application_service

    return build_tonight_application_service()


def _production_weather_provider(latitude: float, longitude: float):
    from astro_score import fetch_weather

    return fetch_weather(latitude, longitude)


def _production_profile_provider():
    from astro_score import load_user_profile

    return load_user_profile()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    *,
    service_factory: Callable = _production_service_factory,
    weather_provider: Callable = _production_weather_provider,
    profile_provider: Callable = _production_profile_provider,
    clock: Callable[[], datetime] = _utc_now,
) -> FastAPI:
    application = FastAPI(title="AstroPilot API", version="1.0.0")
    web_root = Path(__file__).with_name("web")
    application.mount(
        "/ui",
        StaticFiles(directory=web_root),
        name="tonight-ui",
    )

    @application.get("/", include_in_schema=False)
    def tonight_ui():
        return FileResponse(web_root / "index.html")

    @application.post(
        "/v1/tonight",
        response_model=TonightResponseModel,
        summary="Recommend tonight's astrophotography mission",
        description=(
            "Evaluates the next available night and returns a transport-safe "
            "mission enriched with Decision Intelligence: astronomical "
            "quality, productivity, operational risks and season context."
        ),
        responses={
            422: {
                "description": "The request or profile location is invalid.",
                "content": {
                    "application/json": {
                        "examples": {
                            "invalid_request": {
                                "summary": "Bortle value outside the range 1-9",
                                "value": {
                                    "detail": [
                                        {
                                            "type": "less_than_equal",
                                            "loc": ["body", "bortle"],
                                            "msg": "Input should be less than or equal to 9",
                                            "input": 12,
                                            "ctx": {"le": 9},
                                        }
                                    ]
                                },
                            },
                            "invalid_profile_location": {
                                "summary": "Invalid location stored in profile",
                                "value": {
                                    "detail": {
                                        "code": "invalid_profile_location",
                                        "message": "Profile location is invalid.",
                                    }
                                },
                            },
                        }
                    }
                },
            },
            503: {
                "description": (
                    "Weather is unavailable, invalid or insufficient, or the "
                    "snapshot is stale, the selected window is not covered, "
                    "or the tonight forecast is unavailable."
                ),
                "content": {
                    "application/json": {
                        "examples": {
                            "weather_unavailable": {
                                "summary": "Weather provider unavailable",
                                "value": {
                                    "detail": {
                                        "code": "weather_unavailable",
                                        "message": (
                                            "Weather data is temporarily unavailable."
                                        ),
                                    }
                                },
                            },
                            "weather_invalid": {
                                "summary": "Weather response rejected",
                                "value": {
                                    "detail": {
                                        "code": "weather_invalid",
                                        "message": "Weather data failed validation.",
                                    }
                                },
                            },
                            "weather_insufficient": {
                                "summary": "Weather coverage is insufficient",
                                "value": {
                                    "detail": {
                                        "code": "weather_insufficient",
                                        "message": "Weather coverage is insufficient.",
                                    }
                                },
                            },
                            "weather_stale": {
                                "summary": "Weather snapshot is too old",
                                "value": {
                                    "detail": {
                                        "code": "weather_stale",
                                        "message": (
                                            "Weather data is too old for a reliable decision."
                                        ),
                                    }
                                },
                            },
                            "weather_window_uncovered": {
                                "summary": "Mission window is not covered by weather",
                                "value": {
                                    "detail": {
                                        "code": "weather_window_uncovered",
                                        "message": (
                                            "Weather data does not fully cover the "
                                            "selected mission window."
                                        ),
                                    }
                                },
                            },
                            "decision_invalid": {
                                "summary": "Decision consistency check failed",
                                "value": {
                                    "detail": {
                                        "code": "decision_invalid",
                                        "message": (
                                            "The decision failed consistency validation."
                                        ),
                                    }
                                },
                            },
                            "location_timezone_unresolved": {
                                "summary": "Location timezone unresolved",
                                "value": {
                                    "detail": {
                                        "code": "location_timezone_unresolved",
                                        "message": (
                                            "The location timezone could not be resolved."
                                        ),
                                    }
                                },
                            },
                            "forecast_unavailable": {
                                "summary": "Tonight forecast unavailable",
                                "value": {
                                    "detail": {
                                        "code": "forecast_unavailable",
                                        "message": (
                                            "Tonight forecast is temporarily unavailable."
                                        ),
                                    }
                                },
                            },
                        }
                    }
                },
            },
        },
    )
    def tonight(request: TonightRequest):
        profile = dict(profile_provider())
        profile.update(request.profile)
        if request.location is not None:
            profile["location"] = request.location.model_dump()

        raw_location = profile.get(
            "location",
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": 6.5495,
            },
        )
        try:
            location = LocationRequest.model_validate(raw_location).model_dump()
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_profile_location",
                    "message": "Profile location is invalid.",
                },
            ) from exc
        profile["location"] = location

        weather_freshness: WeatherFreshness | None = None
        try:
            weather = weather_provider(
                location["latitude"],
                location["longitude"],
            )
            if isinstance(weather, WeatherSnapshot):
                weather_freshness = validate_weather_freshness(
                    weather,
                    reference_time_utc=clock(),
                )
        except WeatherIngressError as exc:
            messages = {
                "weather_insufficient": "Weather coverage is insufficient.",
                "weather_stale": (
                    "Weather data is too old for a reliable decision."
                ),
            }
            message = messages.get(exc.code, "Weather data failed validation.")
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": message},
            ) from exc
        except LocationTimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": "The location timezone could not be resolved.",
                },
            ) from exc
        if weather is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "weather_unavailable",
                    "message": "Weather data is temporarily unavailable.",
                },
            )

        try:
            result = service_factory().evaluate(
                profile=profile,
                weather=weather,
                equipment=request.equipment,
                goal=request.goal,
                target=request.target,
                bortle=request.bortle,
            )
        except DecisionConsistencyError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": "The decision failed consistency validation.",
                },
            ) from exc
        if result.status is TonightStatus.FORECAST_UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "forecast_unavailable",
                    "message": "Tonight forecast is temporarily unavailable.",
                },
            )

        if (
            result.status is TonightStatus.AVAILABLE
            and isinstance(weather, WeatherSnapshot)
        ):
            try:
                validate_selected_window_weather_coverage(
                    result.mission,
                    weather,
                )
            except WeatherWindowCoverageError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": exc.code,
                        "message": (
                            "Weather data does not fully cover the selected "
                            "mission window."
                        ),
                    },
                ) from exc

        payload = TonightResponse.from_result(result).to_dict()
        if isinstance(weather, WeatherSnapshot):
            payload["weather_trust"] = weather.trust_transport(weather_freshness)
        return payload

    return application


app = create_app()
