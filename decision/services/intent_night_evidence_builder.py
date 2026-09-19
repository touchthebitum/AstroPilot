from datetime import datetime, timezone

from decision.models.context.site_context import SiteContext
from decision.models.intent_night_evidence import IntentNightEvidence
from decision.models.lunar_geometry import LunarGeometry
from decision.services.imaging_field_geometry_resolver import (
    ImagingFieldGeometryResolver,
)
from decision.services.lunar_geometry_service import LunarGeometryService


class IntentNightEvidenceBuildError(ValueError):
    """Raised when complete intent-night evidence cannot be built safely."""


class IntentNightEvidenceBuilder:
    """Build uninterpreted evidence for one actionable night window."""

    def __init__(
        self,
        *,
        geometry_resolver: ImagingFieldGeometryResolver,
        lunar_geometry_service: LunarGeometryService,
    ) -> None:
        self._geometry_resolver = geometry_resolver
        self._lunar_geometry_service = lunar_geometry_service

    def build(
        self,
        *,
        imaging_field_id: str,
        actionable_window_start: datetime,
        actionable_window_end: datetime,
        site: SiteContext,
    ) -> IntentNightEvidence:
        start_utc = self._to_utc(
            actionable_window_start,
            "actionable_window_start",
        )
        end_utc = self._to_utc(
            actionable_window_end,
            "actionable_window_end",
        )
        if end_utc <= start_utc:
            raise IntentNightEvidenceBuildError(
                "actionable_window_end must be after actionable_window_start"
            )
        if not isinstance(site, SiteContext):
            raise IntentNightEvidenceBuildError(
                "site must be a SiteContext"
            )

        window_duration = end_utc - start_utc
        actionable_duration_hours = (
            window_duration.total_seconds() / 3600.0
        )
        reference_time = start_utc + window_duration / 2

        try:
            field_geometry = self._geometry_resolver.resolve(
                imaging_field_id
            )
        except Exception as error:
            raise IntentNightEvidenceBuildError(
                "failed to resolve imaging-field geometry"
            ) from error

        try:
            lunar_geometry = self._lunar_geometry_service.calculate(
                reference_time=reference_time,
                site=site,
                field_geometry=field_geometry,
            )
        except Exception as error:
            raise IntentNightEvidenceBuildError(
                "failed to calculate lunar geometry"
            ) from error

        if not isinstance(lunar_geometry, LunarGeometry):
            raise IntentNightEvidenceBuildError(
                "lunar geometry service returned an invalid result"
            )

        try:
            return IntentNightEvidence(
                imaging_field_id=imaging_field_id,
                actionable_window_start=actionable_window_start,
                actionable_window_end=actionable_window_end,
                actionable_duration_hours=actionable_duration_hours,
                reference_time=reference_time,
                moon_illumination=lunar_geometry.moon_illumination,
                moon_altitude_deg=lunar_geometry.moon_altitude_deg,
                moon_separation_deg=lunar_geometry.moon_separation_deg,
            )
        except (TypeError, ValueError) as error:
            raise IntentNightEvidenceBuildError(
                "failed to construct intent-night evidence"
            ) from error

    @staticmethod
    def _to_utc(value: datetime, name: str) -> datetime:
        if not isinstance(value, datetime):
            raise IntentNightEvidenceBuildError(
                f"{name} must be a datetime"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise IntentNightEvidenceBuildError(
                f"{name} must be timezone-aware"
            )
        return value.astimezone(timezone.utc)
