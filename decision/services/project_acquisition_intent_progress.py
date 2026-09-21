import math
from collections.abc import Mapping
from fractions import Fraction

from decision.services.imaging_field_resolver import ImagingFieldResolver
from decision.services.project_imaging_field_resolution import (
    ProjectImagingFieldResolutionError,
    resolve_project_imaging_field,
)


class ProjectAcquisitionIntentProgressError(ValueError):
    """Invalid explicit progress for a project's acquisition intents."""


def _finite_number(value, *, positive=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        # Integers outside the finite-float range cannot be projected safely.
        return False


def calculated_duration_seconds(frames: int, exposure_seconds: int | float) -> float:
    """Multiply exactly first; expose only a finite, representable float.

    Fraction preserves the binary value of a float exposure, even when the
    frame count itself cannot be converted to float. Inputs are validated by
    resolve_project_acquisition_intent_progress before this helper is used.
    """
    try:
        seconds = float(Fraction(frames) * Fraction(exposure_seconds))
    except OverflowError as exc:
        raise ValueError("calculated duration must be finite") from exc
    if not math.isfinite(seconds):
        raise ValueError("calculated duration must be finite")
    return seconds


def resolve_project_acquisition_intent_progress(
    project: Mapping[str, object], resolver: ImagingFieldResolver,
) -> tuple[dict, ...]:
    if "acquisition_intent_progress" not in project:
        return ()
    entries = project["acquisition_intent_progress"]
    if not isinstance(entries, (list, tuple)):
        raise ProjectAcquisitionIntentProgressError("progress must be a list")
    try:
        field = resolve_project_imaging_field(project, resolver)
    except ProjectImagingFieldResolutionError as error:
        raise ProjectAcquisitionIntentProgressError("invalid imaging_field_id") from error
    if field is None:
        raise ProjectAcquisitionIntentProgressError("progress requires imaging_field_id")
    known = {intent.acquisition_intent_id for intent in field.acquisition_intents}
    seen = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ProjectAcquisitionIntentProgressError("progress entry must be an object")
        keys = set(entry)
        detailed = {"acquisition_intent_id", "acquired_frames", "exposure_seconds"}
        manual = {"acquisition_intent_id", "acquired_duration_manual"}
        if keys not in (detailed, manual):
            raise ProjectAcquisitionIntentProgressError("progress requires exactly one complete source")
        intent_id = entry["acquisition_intent_id"]
        if not isinstance(intent_id, str) or not intent_id.strip() or intent_id not in known:
            raise ProjectAcquisitionIntentProgressError("intent does not belong to imaging field")
        if intent_id in seen:
            raise ProjectAcquisitionIntentProgressError("duplicate acquisition_intent_id")
        seen.add(intent_id)
        if keys == detailed:
            frames = entry["acquired_frames"]
            if not isinstance(frames, int) or isinstance(frames, bool) or frames < 0:
                raise ProjectAcquisitionIntentProgressError("acquired_frames must be a nonnegative integer")
            if not _finite_number(entry["exposure_seconds"], positive=True):
                raise ProjectAcquisitionIntentProgressError("exposure_seconds must be finite and positive")
            try:
                calculated_duration_seconds(frames, entry["exposure_seconds"])
            except ValueError as exc:
                raise ProjectAcquisitionIntentProgressError("calculated duration must be finite") from exc
        elif not _finite_number(entry["acquired_duration_manual"]):
            raise ProjectAcquisitionIntentProgressError("manual duration must be finite and nonnegative")
    return tuple(dict(entry) for entry in entries)
