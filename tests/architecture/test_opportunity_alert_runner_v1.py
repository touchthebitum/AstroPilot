from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import ast
import inspect

import pytest
from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment, START
from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger
from decision.models.opportunity_alert import OpportunityAlertPolicy
from decision.services.tonight_application_service import TonightResult, TonightStatus
from decision.runners.opportunity_alert_runner import (
    OpportunityAlertRunner, OpportunityAlertCadence, OpportunityAlertCycleStatus as Status,
)


def runner(result, directory):
    service = Mock()
    service.evaluate.return_value = result
    return OpportunityAlertRunner(tonight_service=service,
        ledger=FileOpportunityAlertLedger(directory)), service


def cycle(r, p, at=START):
    return r.run_cycle(policy=p, logical_time=at, profile={}, weather=None, bortle=4)


def test_disabled_skips_io(complete, tmp_path):
    r, service = runner(complete, tmp_path)
    result = cycle(r, OpportunityAlertPolicy())
    assert result.status is Status.NO_ALERT and not result.evaluated
    assert result.reason_codes == ('alerts_disabled',)
    service.evaluate.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_once_repeat_and_restart(complete, policy, tmp_path):
    r, service = runner(complete, tmp_path)
    first = cycle(r, policy)
    assert first.status is Status.ALERT_EMITTED and first.evaluated
    assert first.alert.logical_time == START
    service.evaluate.assert_called_once_with(profile={}, weather=None, bortle=4,
        reference_time_utc=START)
    assert cycle(r, policy).status is Status.NO_ALERT
    restarted, _ = runner(complete, tmp_path)
    assert cycle(restarted, policy).reason_codes == ('duplicate_or_cooldown',)


def shift(result, delta, identity):
    value = result.alert_mission_input
    return replace(result, timeline_start=result.timeline_start + delta,
        alert_mission_input=replace(value, window_start=value.window_start + delta,
            window_end=value.window_end + delta, decision_id=identity, selection_id=identity),
        alert_assessment=replace(result.alert_assessment, window_start=value.window_start + delta,
            window_end=value.window_end + delta),
        mission=replace(result.mission, window_start=result.mission.window_start + delta,
            window_end=result.mission.window_end + delta, decision_id=identity, selection_id=identity))


def test_new_opportunity_cooldown(complete, policy, tmp_path):
    r, service = runner(complete, tmp_path)
    assert cycle(r, policy).alert
    service.evaluate.return_value = shift(complete, timedelta(hours=1), 'next')
    assert cycle(r, policy, START + timedelta(hours=1)).reason_codes == ('duplicate_or_cooldown',)
    service.evaluate.return_value = shift(complete, timedelta(days=1), 'tomorrow')
    assert cycle(r, policy, START + timedelta(days=1)).alert


def test_corruption_preserved(complete, policy, tmp_path):
    path = tmp_path / 'opportunity_alert_ledger.json'
    path.write_text('{broken')
    r, _ = runner(complete, tmp_path)
    result = cycle(r, policy)
    assert result.status is Status.ERROR and result.alert is None and result.evaluated
    assert result.reason_codes == ('opportunity_alert_claim_failed',)
    assert path.read_text() == '{broken'


@pytest.mark.parametrize('damage', ['evidence', 'availability', 'aqi'])
def test_insufficient_evidence(complete, policy, tmp_path, damage):
    if damage == 'evidence':
        complete = replace(complete, forecast_evidence=None)
    elif damage == 'availability':
        complete = replace(complete, alert_mission_input=replace(complete.alert_mission_input, availability=None))
    else:
        complete = replace(complete, mission=replace(complete.mission,
            astro_quality=replace(complete.mission.astro_quality, decision_eligible=False)))
    r, _ = runner(complete, tmp_path)
    assert cycle(r, policy).status is Status.NO_ALERT
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('status', list(TonightStatus))
def test_tonight_refusals(policy, tmp_path, status):
    if status is TonightStatus.AVAILABLE:
        return
    r, _ = runner(TonightResult(None, None, None, status=status), tmp_path)
    result = cycle(r, policy)
    assert result.status is (Status.ERROR if status is TonightStatus.FORECAST_UNAVAILABLE else Status.NO_ALERT)
    assert result.alert is None


def test_tonight_exception_and_invalid_output(policy, tmp_path):
    r, service = runner(None, tmp_path)
    assert cycle(r, policy).status is Status.ERROR
    service.evaluate.side_effect = RuntimeError('private details')
    result = cycle(r, policy)
    assert result.reason_codes == ('tonight_evaluation_failed',) and not result.evaluated
    assert not list(tmp_path.iterdir())


def test_invalid_time_and_override(policy, tmp_path):
    r, service = runner(None, tmp_path)
    assert cycle(r, policy, datetime(2026, 1, 1)).status is Status.ERROR
    assert r.run_cycle(policy=policy, logical_time=START, reference_time_utc=START).status is Status.ERROR
    service.evaluate.assert_not_called()


def test_cadence():
    cadence = OpportunityAlertCadence(timedelta(minutes=15))
    assert cadence.is_due(START, None)
    assert not cadence.is_due(START + timedelta(minutes=14), START)
    assert cadence.is_due(START + timedelta(minutes=15), START)
    assert not cadence.is_due(START - timedelta(minutes=1), START)
    assert cadence.next_due(START) == START + timedelta(minutes=15)
    assert cadence.is_due(START.astimezone(timezone(timedelta(hours=2))), None)
    for invalid in (timedelta(0), timedelta(seconds=-1), 15):
        with pytest.raises(ValueError):
            OpportunityAlertCadence(invalid)
    with pytest.raises(ValueError):
        cadence.is_due(datetime(2026, 1, 1), None)


def test_dependency_boundary():
    import decision.runners.opportunity_alert_runner as module
    tree = ast.parse(inspect.getsource(module))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert set(imports) <= {'dataclasses', 'datetime', 'enum',
        'decision.models.opportunity_alert', 'decision.services.opportunity_alert_service',
        'decision.services.tonight_application_service'}
    assert '.now(' not in inspect.getsource(module)


def test_concurrent_claims(complete, policy, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    r, _ = runner(complete, tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cycle(r, policy), range(16)))
    assert sum(result.status is Status.ALERT_EMITTED for result in results) == 1
    assert all(result.status is not Status.ERROR for result in results)


def test_no_engine_recalculation(complete, policy, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('runner must consume existing Tonight evidence')
    monkeypatch.setattr('decision.mission.mission_assembler.ProductiveWindowAssessment.build', forbidden)
    monkeypatch.setattr('decision.quality.astro_quality_engine.AstroQualityEngine.evaluate', forbidden)
    r, service = runner(complete, tmp_path)
    assert cycle(r, policy).status is Status.ALERT_EMITTED
    service.evaluate.assert_called_once()


def test_result_rejects_alert_mismatch():
    from decision.runners.opportunity_alert_runner import OpportunityAlertCycleResult
    with pytest.raises(ValueError):
        OpportunityAlertCycleResult(Status.ALERT_EMITTED, True, START, ())
