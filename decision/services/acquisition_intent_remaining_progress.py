"""Derive intent progress exclusively from validated, persisted inputs."""

from dataclasses import asdict
import math

from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress
from decision.models.imaging_field import ImagingFieldDefinition
from decision.models.project_acquisition_intent_target import ProjectAcquisitionIntentTarget
from decision.services.project_acquisition_intent_progress import calculated_duration_seconds


def derive_acquisition_intent_remaining_progress(
    imaging_field: ImagingFieldDefinition,
    targets: tuple[ProjectAcquisitionIntentTarget, ...],
    progress: tuple[dict, ...],
) -> tuple[AcquisitionIntentRemainingProgress, ...]:
    by_target = {item.acquisition_intent_id: item.target_hours for item in targets}
    by_progress = {item["acquisition_intent_id"]: item for item in progress}
    result = []
    for intent in imaging_field.acquisition_intents:
        intent_id = intent.acquisition_intent_id
        entry = by_progress.get(intent_id)
        seconds = None
        if entry is not None:
            if "acquired_duration_manual" in entry:
                try:
                    seconds = float(entry["acquired_duration_manual"])
                except OverflowError as exc:
                    raise ValueError("manual duration must be finite") from exc
            else:
                seconds = calculated_duration_seconds(entry["acquired_frames"], entry["exposure_seconds"])
            if not math.isfinite(seconds):
                raise ValueError("calculated duration must be finite")
        hours = seconds / 3600 if seconds is not None else None
        target = by_target.get(intent_id)
        remaining = max(target - hours, 0.0) if target is not None and hours is not None else None
        result.append(AcquisitionIntentRemainingProgress(intent_id, seconds, hours, target, remaining))
    return tuple(result)


def remaining_progress_projection(items: tuple[AcquisitionIntentRemainingProgress, ...]) -> list[dict]:
    return [asdict(item) for item in items]
