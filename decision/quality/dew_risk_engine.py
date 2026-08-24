import math

from decision.quality.dew_risk_result import DewRiskResult


class DewRiskEngine:
    @staticmethod
    def _dew_point_c(
        temperature_c: float,
        humidity_percent: float,
    ) -> float:
        humidity = max(
            1.0,
            min(100.0, humidity_percent),
        )

        a = 17.62
        b = 243.12

        gamma = (
            math.log(humidity / 100.0)
            + (a * temperature_c)
            / (b + temperature_c)
        )

        return (
            b * gamma
            / (a - gamma)
        )

    @staticmethod
    def evaluate(
        temperature_c: float,
        humidity_percent: float,
    ) -> DewRiskResult:
        dew_point = DewRiskEngine._dew_point_c(
            temperature_c,
            humidity_percent,
        )

        spread = temperature_c - dew_point

        if spread < 1.0:
            risk = "CRITICAL"
            score = 20.0
        elif spread < 3.0:
            risk = "HIGH"
            score = 45.0
        elif spread < 5.0:
            risk = "MEDIUM"
            score = 70.0
        else:
            risk = "LOW"
            score = 100.0

        return DewRiskResult(
            dew_point_c=round(dew_point, 1),
            spread_c=round(spread, 1),
            risk=risk,
            score=score,
        )