from types import SimpleNamespace

import pytest

from decision.rules.cloud_rule import CloudRule
from decision.rules.seeing_rule import SeeingRule


def _context(*, cloud_cover=0.0, seeing_arcsec=1.5):
    return SimpleNamespace(
        weather=SimpleNamespace(
            cloud_cover=cloud_cover,
            seeing_arcsec=seeing_arcsec,
        ),
    )


@pytest.mark.parametrize(
    ("cloud_cover", "expected_score"),
    [
        (0.0, 0),
        (9.99, 0),
        (10.0, -3),
        (19.99, -3),
        (20.0, -8),
        (29.99, -8),
        (30.0, -15),
        (39.99, -15),
        (40.0, -22),
        (59.99, -22),
        (60.0, -35),
        (79.99, -35),
        (80.0, -50),
        (100.0, -50),
    ],
)
def test_cloud_rule_penalty_boundaries(cloud_cover, expected_score):
    contribution = CloudRule().evaluate(
        _context(cloud_cover=cloud_cover),
        profile=object(),
    )

    assert contribution.rule == "Cloud"
    assert contribution.score == expected_score
    assert contribution.confidence == 1.0
    assert contribution.reason == "Couverture nuageuse"
    assert contribution.details == (
        f"Nuages pondérés : {cloud_cover:.1f} %"
    )


@pytest.mark.parametrize(
    ("seeing", "expected_score", "expected_reason"),
    [
        (1.2, 15, 'Seeing exceptionnel (1.2")'),
        (1.21, 10, 'Très bon seeing (1.2")'),
        (1.8, 10, 'Très bon seeing (1.8")'),
        (1.81, 5, 'Bon seeing (1.8")'),
        (2.3, 5, 'Bon seeing (2.3")'),
        (2.31, 0, 'Seeing moyen (2.3")'),
        (3.0, 0, 'Seeing moyen (3.0")'),
        (3.01, -10, 'Seeing médiocre (3.0")'),
    ],
)
def test_seeing_rule_score_boundaries(
    seeing,
    expected_score,
    expected_reason,
):
    contribution = SeeingRule().evaluate(
        _context(seeing_arcsec=seeing),
        profile=object(),
    )

    assert contribution.rule == "Seeing"
    assert contribution.score == expected_score
    assert contribution.confidence == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == ""


def test_seeing_rule_reports_missing_measurement_with_low_confidence():
    contribution = SeeingRule().evaluate(
        _context(seeing_arcsec=None),
        profile=object(),
    )

    assert contribution.rule == "Seeing"
    assert contribution.score == 0
    assert contribution.confidence == 0.3
    assert contribution.reason == "Seeing indisponible"
    assert contribution.details == "Seeing : None"
