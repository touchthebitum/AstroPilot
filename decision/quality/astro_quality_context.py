from dataclasses import dataclass


@dataclass(frozen=True)
class AstroQualityContext:
    target_altitude_deg: float
    cloud_cover_percent: float
    moon_penalty: float
    seeing_arcsec: float | None
    image_quality_score: float | None