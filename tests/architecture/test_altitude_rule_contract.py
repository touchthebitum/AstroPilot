from types import SimpleNamespace

import pytest

from decision.rules.altitude_rule import AltitudeRule


@pytest.mark.parametrize(
    ("altitude", "expected_score", "expected_reason"),
    [
        (0.0, -15, "Objet trop bas"),
        (29.99, -15, "Objet trop bas"),
        (30.0, 0, "Altitude correcte"),
        (49.99, 0, "Altitude correcte"),
        (50.0, 8, "Bonne altitude"),
        (69.99, 8, "Bonne altitude"),
        (70.0, 15, "Altitude excellente"),
        (90.0, 15, "Altitude excellente"),
    ],
)
def test_altitude_rule_score_boundaries(
    altitude,
    expected_score,
    expected_reason,
):
    project = SimpleNamespace(
        sky=SimpleNamespace(target_altitude_deg=altitude),
    )

    contribution = AltitudeRule().evaluate(
        project,
        context=object(),
    )

    assert contribution.rule == "Altitude"
    assert contribution.score == expected_score
    assert contribution.confidence == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == f"Altitude : {altitude:.1f}°"
    assert contribution.weight == 1.0
