from datetime import timedelta

from decision.field_observation import FieldObservation
from decision.weather.cloud_forecast_evidence_comparison import (
    SelectedCloudForecastComparison,
    compare_cloud_forecast_evidence,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


def compare_cloud_forecast_to_field_observation(
    evidence: DecisionForecastEvidence,
    observation: FieldObservation,
    *,
    maximum_absolute_offset: timedelta,
) -> SelectedCloudForecastComparison | None:
    if observation.cloud_condition is None:
        return None

    return compare_cloud_forecast_evidence(
        evidence,
        observation.observed_at_utc,
        observation.cloud_condition,
        maximum_absolute_offset=maximum_absolute_offset,
    )
