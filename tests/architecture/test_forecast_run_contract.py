from dataclasses import FrozenInstanceError

import pytest

from decision.forecast.forecast_run import ForecastRun
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


def test_forecast_run_is_immutable_stores_nights_as_tuple_and_preserves_evidence():
    nights = [{"date": "2026-09-01"}]
    evidence = DecisionForecastEvidence(())

    run = ForecastRun(nights=nights, evidence=evidence)

    assert run.nights == tuple(nights)
    assert run.evidence is evidence
    with pytest.raises(FrozenInstanceError):
        run.nights = ()


def test_forecast_run_requires_explicit_legacy_evidence_absence():
    run = ForecastRun(nights=[], evidence=None)

    assert run.nights == ()
    assert run.evidence is None
