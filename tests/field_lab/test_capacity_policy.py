"""Portable sizing; storage/locking boundaries run in POSIX CI."""
import pytest

from astropilot.field_lab_capacity import capacity_policy


@pytest.mark.parametrize("ceiling, soft, stop, reserve, effective", [
    (1, 1, 0, 0, 0),
    (10, 10, 9, 1, 8),
    (20000, 20000, 18000, 3000, 15000),
    (100000, 100000, 90000, 15000, 75000),
    (300000, 300000, 270000, 15000, 255000),
    (2000000, 300000, 270000, 15000, 255000),
])
def test_configured_enumeration_ceiling_still_bounds_policy(ceiling, soft, stop, reserve, effective):
    assert capacity_policy(ceiling) == dict(operational_soft_limit=soft, stop_at=stop,
        reserved_budget=reserve, effective_stop_at=effective)
    assert stop <= ceiling and effective + reserve == stop


def test_proposed_six_week_envelope_keeps_full_batch_reserve():
    policy = capacity_policy(2000000)
    projected_count = 17999 + 42 * 5000
    assert projected_count < policy["effective_stop_at"]
    assert projected_count + policy["reserved_budget"] < policy["stop_at"]
