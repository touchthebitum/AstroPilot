from __future__ import annotations

from datetime import datetime
import socket
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from astropilot.catalog import CATALOG
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.equipment.camera import Camera
from decision.models.equipment.imaging_filter import ImagingFilter
from decision.models.equipment.imaging_optics import ImagingOptics
from decision.models.equipment.imaging_setup import ImagingSetup
from decision.models.equipment.mount import Mount
from decision.weather.weather_forecast import WeatherForecast


@pytest.fixture(autouse=True)
def block_live_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test fail immediately if production code opens a socket."""

    def deny_connection(*args, **kwargs):
        raise AssertionError("Live network access is forbidden in tests")

    monkeypatch.setattr(socket.socket, "connect", deny_connection)
    monkeypatch.setattr(socket, "create_connection", deny_connection)


@pytest.fixture
def frozen_time() -> datetime:
    return datetime(
        2026,
        10,
        15,
        22,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )


@pytest.fixture
def buttes_site() -> SimpleNamespace:
    return SimpleNamespace(
        name="Buttes",
        latitude=46.7508,
        longitude=6.5495,
        elevation=770,
        bortle=4,
        sqm=20.8,
    )


@pytest.fixture
def m31_target() -> dict:
    return dict(CATALOG["M31"])


@pytest.fixture
def frozen_weather() -> WeatherForecast:
    return WeatherForecast(
        hourly=[],
        hourly_clouds=[73.0],
        hourly_humidity=[91.0],
        hourly_wind=[27.0],
        hourly_seeing=[3.2],
        hourly_moon_penalty=[0.85],
        hourly_temperature=[4.0],
        hourly_visibility=[12_000.0],
    )


@pytest.fixture
def frozen_equipment() -> EquipmentContext:
    return EquipmentContext(
        setup=ImagingSetup(
            mount=Mount(
                manufacturer="ZWO",
                model="AM3",
                payload_capacity_kg=13.0,
            ),
            optics=ImagingOptics(
                manufacturer="Samyang",
                model="135mm",
                focal_length_mm=135.0,
                aperture_mm=48.0,
                focal_ratio=2.8,
            ),
            camera=Camera(
                manufacturer="ZWO",
                model="ASI183MM",
                pixel_size_um=2.4,
                sensor_width_px=5496,
                sensor_height_px=3672,
                monochrome=True,
            ),
            filter=ImagingFilter(
                manufacturer="Baader",
                name="H-alpha 6.5nm",
                filter_type="narrowband",
                bandwidth_nm=6.5,
                central_wavelength_nm=656.3,
            ),
        )
    )


@pytest.fixture
def frozen_portfolio() -> PortfolioContext:
    return PortfolioContext(
        active_projects=3,
        total_remaining_hours=44.0,
        highest_priority=80,
        average_progress=25.0,
    )

