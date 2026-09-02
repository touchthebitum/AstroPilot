from dataclasses import dataclass

from decision.field_observation import CloudCondition


@dataclass(frozen=True)
class CloudForecastComparison:
    forecast_condition: CloudCondition
    observed_condition: CloudCondition


def compare_cloud_conditions(
    forecast_condition: CloudCondition,
    observed_condition: CloudCondition,
) -> CloudForecastComparison:
    return CloudForecastComparison(
        forecast_condition=forecast_condition,
        observed_condition=observed_condition,
    )
