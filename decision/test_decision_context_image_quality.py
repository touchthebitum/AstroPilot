from datetime import datetime, timedelta

from decision.engines.image_quality_engine import ImageQualityEngine

from decision.models.context.decision_context import DecisionContext
from decision.models.context.session_context import SessionContext
from decision.models.context.site_context import SiteContext
from decision.models.context.weather_context import WeatherContext
from decision.models.context.sky_context import SkyContext
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.context.preferences_context import PreferencesContext

from decision.models.sky.celestial_object import CelestialObject
from decision.models.equipment.camera import Camera
from decision.models.equipment.mount import Mount
from decision.models.equipment.imaging_optics import ImagingOptics
from decision.models.equipment.imaging_filter import ImagingFilter
from decision.models.equipment.imaging_setup import ImagingSetup


camera = Camera("ZWO", "ASI183MM", 2.4, 5496, 3672, True)
optics = ImagingOptics("Samyang", "135mm", 135, 48, 2.8)
mount = Mount("ZWO", "AM3")
ha_filter = ImagingFilter("Baader", "H-alpha 6.5nm", "narrowband", 6.5, 656.3)

setup = ImagingSetup(
    mount=mount,
    optics=optics,
    camera=camera,
    filter=ha_filter,
)

target = CelestialObject("IC1396", "nebula", 170)

context = DecisionContext(
    session=SessionContext(
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=3),
        available_duration=timedelta(hours=3),
    ),
    site=SiteContext(
        name="Buttes",
        latitude=46.75,
        longitude=6.55,
        elevation=770,
        bortle=4,
        sqm=21.0,
    ),
    equipment=EquipmentContext(setup=setup),
    weather=WeatherContext(
        cloud_cover=4,
        humidity=46,
        wind_speed_kmh=4.5,
        seeing_arcsec=1.5,
    ),
    sky=SkyContext(
        target=target,
        moon_illumination=45,
        moon_separation_deg=85,
        target_altitude_deg=62,
        astronomical_darkness=True,
    ),
    portfolio=PortfolioContext(
        active_projects=1,
        total_remaining_hours=15,
        highest_priority=80,
        average_progress=0,
    ),
    preferences=PreferencesContext(
        astro_weight=0.7,
        project_weight=0.3,
        minimum_altitude_deg=30,
        minimum_sqm=20,
    ),
)

result = ImageQualityEngine.evaluate(context)

print(result)
print(result.metrics)
