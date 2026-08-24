from decision.quality.dew_risk_engine import DewRiskEngine


def test_dew_risk_is_low_with_large_temperature_spread():
    result = DewRiskEngine.evaluate(
        temperature_c=10.0,
        humidity_percent=50.0,
    )

    assert result.risk == "LOW"
    assert result.spread_c >= 5.0
    assert result.score == 100.0


def test_dew_risk_becomes_critical_near_saturation():
    result = DewRiskEngine.evaluate(
        temperature_c=5.0,
        humidity_percent=98.0,
    )

    assert result.risk == "CRITICAL"
    assert result.spread_c < 1.0
    assert result.score == 20.0


def test_dew_risk_orders_intermediate_conditions():
    medium = DewRiskEngine.evaluate(
        temperature_c=8.0,
        humidity_percent=75.0,
    )

    high = DewRiskEngine.evaluate(
        temperature_c=8.0,
        humidity_percent=90.0,
    )

    assert medium.score > high.score