from __future__ import annotations

from typing import Callable, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

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
    target: str = "deep_sky"
    bortle: int = Field(default=3, ge=1, le=9)


class TonightReasonModel(BaseModel):
    title: str
    severity: str
    value: str | None = None


class TonightFilterModel(BaseModel):
    name: str
    filter_type: str
    bandwidth_nm: float | None = None


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

        location = profile.get(
            "location",
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": 6.5495,
            },
        )
        weather = weather_provider(
            location["latitude"],
            location["longitude"],
        )
        result = service_factory().evaluate(
            profile=profile,
            weather=weather,
            equipment=request.equipment,
            goal=request.goal,
            target=request.target,
            bortle=request.bortle,
        )
        return TonightResponse.from_result(result).to_dict()

    return application


app = create_app()
