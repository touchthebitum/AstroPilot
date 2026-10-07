from dataclasses import dataclass


@dataclass(frozen=True)
class AstroQualityContext:
    target_altitude_deg: float | None
    cloud_cover_percent: float | None
    moon_penalty: float | None
    seeing_arcsec: float | None
    image_quality_score: float | None
    dew_score: float | None = None
