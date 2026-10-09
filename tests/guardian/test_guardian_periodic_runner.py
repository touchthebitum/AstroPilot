from dataclasses import replace, FrozenInstanceError
from datetime import datetime, timezone
from unittest.mock import Mock
import ast
from pathlib import Path
import pytest
from decision.models.guardian import (
    GuardianObservation, GuardianEvidence, GuardianSessionContext,
    GuardianRiskLevel as Risk, GuardianAction as Action, GuardianSessionState,
)
from decision.models.guardian_cycle import GuardianCycleStatus as Status
from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
from decision.runners.guardian_runner import GuardianRunner
from decision.services.guardian_service import assess_guardian

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)

def healthy():
    return GuardianObservation(**{k: GuardianEvidence(v, 'injected', 'OBSERVATION', NOW)
        for k, v in dict(rain_active=False, rain_eta_minutes=None, wind_kmh=0,
                        gust_kmh=0, humidity_percent=40, dew_spread_c=10).items()})

def setup(observation=None, *, evidence=None, session=None, runner=None):
    evidence = evidence if evidence is not None else Mock(return_value=observation or healthy())
    session = session if session is not None else Mock(return_value=GuardianSessionContext(True, NOW))
    service = Mock(wraps=assess_guardian)
    runner = runner if runner is not None else GuardianRunner(evaluator=service)
    return GuardianPeriodicRunner(evidence_provider=evidence, session_context_provider=session,
                                  guardian_runner=runner), evidence, session, service

@pytest.mark.parametrize('observation,risk,action', [
    (healthy(), Risk.SAFE, Action.CONTINUE),
    (replace(healthy(), rain_active=GuardianEvidence(True, 'injected', 'OBSERVATION', NOW)), Risk.CRITICAL, Action.STOP_SESSION),
    (GuardianObservation(), Risk.UNKNOWN, Action.EMERGENCY_STOP),
])
def test_cycle_and_once(observation, risk, action):
    runner, evidence, session, service = setup(observation)
    result = runner.run_cycle(logical_time=NOW)
    assert result.status is Status.ASSESSED
    assert result.assessment.risk_level is risk
    assert result.recommended_action is action
    assert result.logical_time == result.assessment.assessed_at == NOW
    evidence.assert_called_once_with(NOW)
    session.assert_called_once_with(NOW)
    assert service.call_count == 1
    assert service.call_args.kwargs['now'] == NOW
    assert result.assessment.hardware_action is None
    with pytest.raises(FrozenInstanceError): result.status = Status.ERROR

@pytest.mark.parametrize('provider', [Mock(side_effect=RuntimeError('secret')), Mock(return_value=None), Mock(return_value={})])
def test_evidence_failure(provider):
    runner, evidence, session, service = setup(evidence=provider)
    result = runner.run_cycle(logical_time=NOW)
    assert result.status is Status.ERROR and result.assessment is None
    assert result.errors == ('evidence_provider_error',)
    assert not result.decision_eligible
    assert result.recommended_action is Action.EMERGENCY_STOP
    evidence.assert_called_once_with(NOW)
    session.assert_called_once_with(NOW)
    service.assert_not_called()

@pytest.mark.parametrize('rain', [False, True])
def test_session_failure_preserves_risk(rain):
    obs = replace(healthy(), rain_active=GuardianEvidence(rain, 'injected', 'OBSERVATION', NOW))
    runner, _, session, service = setup(obs, session=Mock(side_effect=RuntimeError('secret')))
    result = runner.run_cycle(logical_time=NOW)
    assert result.status is Status.ERROR
    assert result.errors == ('session_provider_error',)
    assert result.assessment.session_state is GuardianSessionState.UNKNOWN
    assert result.assessment.risk_level is (Risk.CRITICAL if rain else Risk.SAFE)
    assert result.recommended_action is Action.EMERGENCY_STOP
    assert not result.decision_eligible and service.call_count == 1
    session.assert_called_once_with(NOW)

def test_unknown_session_is_valid():
    runner, *_ = setup(session=Mock(return_value=None))
    result = runner.run_cycle(logical_time=NOW)
    assert result.status is Status.ASSESSED
    assert result.assessment.session_state is GuardianSessionState.UNKNOWN

@pytest.mark.parametrize('value', [{}, False])
def test_wrong_session_type(value):
    runner, *_ = setup(session=Mock(return_value=value))
    assert runner.run_cycle(logical_time=NOW).errors == ('session_provider_error',)

def test_both_provider_failures():
    runner, _, _, service = setup(evidence=Mock(side_effect=RuntimeError()), session=Mock(side_effect=RuntimeError()))
    result = runner.run_cycle(logical_time=NOW)
    assert result.errors == ('evidence_provider_error', 'session_provider_error')
    service.assert_not_called()

@pytest.mark.parametrize('evaluator', [Mock(side_effect=RuntimeError('secret')), Mock(return_value=None)])
def test_evaluation_failure(evaluator):
    dependency = GuardianRunner(evaluator=evaluator)
    runner, *_ = setup(runner=dependency)
    result = runner.run_cycle(logical_time=NOW)
    assert result.status is Status.ERROR and result.assessment is None
    assert result.errors == ('evaluation_error',)
    assert result.recommended_action is Action.EMERGENCY_STOP and not result.decision_eligible
    assert evaluator.call_count == 1

@pytest.mark.parametrize('time', [None, 'now', NOW.replace(tzinfo=None)])
def test_invalid_time_before_acquisition(time):
    runner, evidence, session, service = setup()
    with pytest.raises(ValueError): runner.run_cycle(logical_time=time)
    evidence.assert_not_called(); session.assert_not_called(); service.assert_not_called()

def test_determinism_and_no_state():
    runner, evidence, session, service = setup()
    assert runner.run_cycle(logical_time=NOW) == runner.run_cycle(logical_time=NOW)
    assert evidence.call_count == session.call_count == service.call_count == 2

@pytest.mark.parametrize('channel', list(healthy().__dataclass_fields__))
@pytest.mark.parametrize('rain', [False, True])
def test_removing_evidence_never_improves(channel, rain):
    obs = replace(healthy(), rain_active=GuardianEvidence(rain, 'injected', 'OBSERVATION', NOW))
    baseline = setup(obs)[0].run_cycle(logical_time=NOW)
    removed = setup(replace(obs, **{channel: None}))[0].run_cycle(logical_time=NOW)
    assert removed.status is Status.ASSESSED
    assert removed.assessment.risk_level >= baseline.assessment.risk_level
    assert removed.recommended_action is Action.EMERGENCY_STOP
    assert not removed.decision_eligible

def test_process_control_exception_propagates():
    runner, *_ = setup(evidence=Mock(side_effect=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): runner.run_cycle(logical_time=NOW)

def test_architecture():
    root = Path(__file__).resolve().parents[2]
    allowed = {'dataclasses', 'datetime', 'enum', 'typing', 'decision.models.guardian',
               'decision.models.guardian_cycle', 'decision.runners.guardian_runner'}
    for path in ['decision/models/guardian_cycle.py', 'decision/runners/guardian_periodic_runner.py']:
        tree = ast.parse((root/path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): assert all(n.name in allowed for n in node.names)
            if isinstance(node, ast.ImportFrom): assert node.module in allowed
            if isinstance(node, ast.Call):
                assert not (isinstance(node.func, ast.Name) and node.func.id in {'open', '__import__', 'eval', 'exec'})
                assert not (isinstance(node.func, ast.Attribute) and node.func.attr in {'now', 'utcnow', 'sleep'})
        assert not any(isinstance(n, (ast.While, ast.AsyncFunctionDef)) for n in ast.walk(tree))

def test_no_file_network_or_process_io(monkeypatch):
    import builtins
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected I/O')
    runner, *_ = setup()
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    result = runner.run_cycle(logical_time=NOW)
    assert result.status is Status.ASSESSED
    assert result.recommended_action is Action.CONTINUE

def test_guardian_runner_called_once_with_exact_inputs():
    observation = healthy()
    context = GuardianSessionContext(True, NOW)
    dependency = Mock(wraps=GuardianRunner())
    runner, *_ = setup(observation, session=Mock(return_value=context), runner=dependency)
    runner.run_cycle(logical_time=NOW)
    dependency.evaluate.assert_called_once_with(observation, now=NOW, session_context=context)
