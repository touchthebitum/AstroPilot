from __future__ import annotations

from typing import Callable, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from decision.services.tonight_application_service import TonightStatus
from decision.services.tonight_response import TonightResponse


class LocationRequest(BaseModel):
    name: str = "Buttes"
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class TonightRequest(BaseModel):
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
    confidence: float
    label: str
    limiting_factor: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class TonightResponseModel(BaseModel):
    status: str
    night_date: str | None = None
    target: str | None = None
    catalog_key: str | None = None
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
    reasons: list[TonightReasonModel] = Field(default_factory=list)


def _production_service_factory():
    from astro_score import build_tonight_application_service

    return build_tonight_application_service()


def _production_weather_provider(latitude: float, longitude: float):
    from astro_score import fetch_weather

    return fetch_weather(latitude, longitude)


def create_app(
    *,
    service_factory: Callable = _production_service_factory,
    weather_provider: Callable = _production_weather_provider,
) -> FastAPI:
    application = FastAPI(title="AstroPilot API", version="1.0.0")

    @application.post(
        "/v1/tonight",
        response_model=TonightResponseModel,
    )
    def tonight(request: TonightRequest):
        profile = dict(request.profile)
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

        weather = weather_provider(
            location["latitude"],
            location["longitude"],
        )
        if weather is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "weather_unavailable",
                    "message": "Weather data is temporarily unavailable.",
                },
            )

        result = service_factory().evaluate(
            profile=profile,
            weather=weather,
            equipment=request.equipment,
            goal=request.goal,
            target=request.target,
            bortle=request.bortle,
        )
        if result.status is TonightStatus.FORECAST_UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "forecast_unavailable",
                    "message": "Tonight forecast is temporarily unavailable.",
                },
            )

        return TonightResponse.from_result(result).to_dict()

    return application


app = create_app()
