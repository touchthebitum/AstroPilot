"""Historical inputs and outputs captured at the lunar comparison boundary.

These values are evidence, never a request to recompute an estimate. Optical
profile definitions remain separate; only the estimator's spectral inputs are
copied so later edits to those definitions cannot alter historical evidence.
"""
from dataclasses import dataclass

from decision.models.intent_night_evidence import IntentNightEvidence
from decision.models.lunar_contamination_estimate import LunarContaminationEstimate
from decision.models.equipment.filter_optical_profile import FilterOpticalProfile


@dataclass(frozen=True, slots=True)
class IntentLunarEstimateSnapshot:
    acquisition_intent_id: str
    filter_profile_id: str
    central_wavelength_nm: float
    fwhm_nm: float
    estimate: LunarContaminationEstimate

    def __post_init__(self):
        FilterOpticalProfile._validate_non_empty_string(self.acquisition_intent_id, "acquisition_intent_id")
        FilterOpticalProfile._validate_non_empty_string(self.filter_profile_id, "filter_profile_id")
        FilterOpticalProfile._validate_positive_number(self.central_wavelength_nm, "central_wavelength_nm")
        FilterOpticalProfile._validate_positive_number(self.fwhm_nm, "fwhm_nm")
        if not isinstance(self.estimate, LunarContaminationEstimate):
            raise TypeError("lunar_estimate_required")
        if self.filter_profile_id != self.estimate.filter_profile_id:
            raise ValueError("lunar_snapshot_profile_mismatch")


@dataclass(frozen=True, slots=True)
class LunarEvidenceSnapshot:
    evidence: IntentNightEvidence
    estimates: tuple[IntentLunarEstimateSnapshot, ...]
    estimator_id: str
    estimator_version: str | None
    comparison_version: str = "pareto-rayleigh-mie-v1"
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported_lunar_snapshot_schema")
        if self.comparison_version != "pareto-rayleigh-mie-v1":
            raise ValueError("unsupported_lunar_comparison_version")
        FilterOpticalProfile._validate_non_empty_string(self.estimator_id, "estimator_id")
        if self.estimator_version is not None:
            FilterOpticalProfile._validate_non_empty_string(self.estimator_version, "estimator_version")
        if not isinstance(self.evidence, IntentNightEvidence):
            raise TypeError("intent_night_evidence_required")
        if any(value is None for value in (self.evidence.moon_illumination,
                self.evidence.moon_altitude_deg, self.evidence.moon_separation_deg)):
            raise ValueError("complete_lunar_snapshot_evidence_required")
        if not isinstance(self.estimates, tuple) or not all(
            isinstance(item, IntentLunarEstimateSnapshot) for item in self.estimates
        ):
            raise TypeError("lunar_snapshot_estimates_must_be_tuple")
        ids = [item.acquisition_intent_id for item in self.estimates]
        if len(ids) < 2 or len(set(ids)) != len(ids):
            raise ValueError("lunar_snapshot_requires_distinct_compared_intents")


def validate_lunar_snapshot(snapshot, *, imaging_field_id=None,
                            acquisition_intent_id=None, eligible_ids=None):
    """Check supplied identities only; never infer evidence from definitions."""
    if snapshot is None:
        return
    if not isinstance(snapshot, LunarEvidenceSnapshot):
        raise TypeError("lunar_evidence_snapshot_required")
    if imaging_field_id is not None and snapshot.evidence.imaging_field_id != imaging_field_id:
        raise ValueError("lunar_snapshot_field_mismatch")
    ids = {item.acquisition_intent_id for item in snapshot.estimates}
    if acquisition_intent_id is not None and acquisition_intent_id not in ids:
        raise ValueError("lunar_snapshot_intent_mismatch")
    if eligible_ids is not None and ids != set(eligible_ids):
        raise ValueError("lunar_snapshot_eligible_intents_mismatch")
