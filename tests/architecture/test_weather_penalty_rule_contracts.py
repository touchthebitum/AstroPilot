from types import SimpleNamespace

import pytest

from decision.rules.humidity_rule import HumidityRule
from decision.rules.visibility_rule import VisibilityRule
from decision.rules.wind_rule import WindRule


def _context(**weather):
    return SimpleNamespace(weather=SimpleNamespace(**weather))


@pytest.mark.parametrize(
    ("wind", "expected_score", "expected_reason"),
    [
        (0.0, 0, "Vent faible"),
        (9.99, 0, "Vent faible"),
        (10.0, -6, "Vent fort"),
        (19.99, -6, "Vent fort"),
        (20.0, -14, "Vent très fort"),
        (29.99, -14, "Vent très fort"),
        (30.0, -25, "Vent très fort"),
    ],
)
def test_wind_rule_penalty_boundaries(
    wind,
    expected_score,
    expected_reason,
):
    contribution = WindRule().evaluate(
        _context(wind_speed_kmh=wind),
        profile=object(),
    )

    assert contribution.rule == "Wind"
    assert contribution.score == expected_score
    assert contribution.confidence == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == f"Vent : {wind:.1f} km/h"


@pytest.mark.parametrize(
    ("humidity", "expected_score", "expected_reason"),
    [
        (0.0, 0, "Humidité idéale"),
        (69.99, 0, "Humidité idéale"),
        (70.0, -8, "Humidité élevée"),
        (84.99, -8, "Humidité élevée"),
        (85.0, -18, "Humidité très élevée"),
        (100.0, -18, "Humidité très élevée"),
    ],
)
def test_humidity_rule_penalty_boundaries(
    humidity,
    expected_score,
    expected_reason,
):
    contribution = HumidityRule().evaluate(
        _context(humidity=humidity),
        profile=object(),
    )

    assert contribution.rule == "Humidity"
    assert contribution.score == expected_score
    assert contribution.confidence == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == f"Humidité : {humidity:.0f} %"


@pytest.mark.parametrize(
    ("visibility", "expected_score", "expected_reason"),
    [
        (25_000.0, 0, "Bonne visibilité"),
        (20_001.0, 0, "Bonne visibilité"),
        (20_000.0, -4, "Visibilité modérée"),
        (10_001.0, -4, "Visibilité modérée"),
        (10_000.0, -10, "Visibilité faible"),
        (5_001.0, -10, "Visibilité faible"),
        (5_000.0, -25, "Visibilité très faible"),
        (0.0, -25, "Visibilité très faible"),
    ],
)
def test_visibility_rule_penalty_boundaries(
    visibility,
    expected_score,
    expected_reason,
):
    contribution = VisibilityRule().evaluate(
        _context(visibility=visibility),
        profile=object(),
    )

    assert contribution.rule == "Visibility"
    assert contribution.score == expected_score
    assert contribution.confidence == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == (
        f"Visibilité : {visibility / 1000:.1f} km"
    )
