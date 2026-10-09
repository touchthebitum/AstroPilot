import json
from datetime import datetime, timedelta, timezone

import pytest

from astropilot.guardian_session_store import GuardianSessionStore, PROVIDER_ID
from astropilot.guardian_host import main, load_config
from decision.models.guardian import GuardianSessionState as State, GuardianObservation, GuardianEvidence
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
from decision.runners.guardian_runner import GuardianRunner

NOW = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)


def attestation(state=State.ACTIVE, stamp=NOW):
    return GuardianLiveSessionEvidence(state, stamp, 'caller_session_heartbeat_v1',
                                       'CALLER_ASSERTED', 'explicit-session')


@pytest.mark.parametrize('state', [State.ACTIVE, State.INACTIVE])
def test_persist_restart_and_expiration(tmp_path, state):
    path = tmp_path / 'local é' / 'session.json'
    GuardianSessionStore(path).write(attestation(state))
    restarted = GuardianSessionStore(path)
    assert restarted(NOW) == attestation(state)
    assert restarted(NOW + timedelta(seconds=900)).state is state
    assert restarted.read(NOW + timedelta(seconds=900, microseconds=1)) is None
    assert restarted.read(NOW - timedelta(microseconds=1)) is None
    assert json.loads(path.read_text())['observed_at'] == NOW.isoformat()


@pytest.mark.parametrize('case', ['absent', 'stale', 'future', 'unknown', 'corrupt',
    'duplicate', 'bool_version', 'schema', 'version', 'source', 'provenance', 'bad_state',
    'naive', 'invalid_date', 'session_id', 'missing', 'extra', 'nonfinite', 'large',
    'invalid_utf8', 'directory', 'null', 'array'])
def test_strict_unavailable_context(tmp_path, case):
    store = GuardianSessionStore(tmp_path / 'session.json')
    store.write(attestation())
    doc = json.loads(store.path.read_text())
    if case == 'absent': store.path.unlink()
    elif case == 'directory':
        store.path.unlink()
        store.path.mkdir()
    elif case == 'corrupt': store.path.write_text('{')
    elif case == 'duplicate': store.path.write_text(store.path.read_text()[:-1] + ', "state":"INACTIVE"}')
    elif case == 'nonfinite': store.path.write_text('{"state": NaN}')
    elif case == 'large': store.path.write_bytes(b' ' * 16385)
    elif case == 'invalid_utf8': store.path.write_bytes(b'\xff')
    elif case == 'null': store.path.write_text('null')
    elif case == 'array': store.path.write_text('[]')
    else:
        if case == 'stale': doc['observed_at'] = (NOW - timedelta(seconds=901)).isoformat()
        elif case == 'future': doc['observed_at'] = (NOW + timedelta(seconds=1)).isoformat()
        elif case == 'unknown': doc['state'] = 'UNKNOWN'
        elif case == 'bool_version': doc['schema_version'] = True
        elif case == 'schema': doc['schema_version'] = 2
        elif case == 'version': doc['version'] = 'v2'
        elif case == 'source': doc['source'] = 'weather'
        elif case == 'provenance': doc['provenance'] = 'INFERRED'
        elif case == 'bad_state': doc['state'] = True
        elif case == 'naive': doc['observed_at'] = '2026-10-09T16:00:00'
        elif case == 'invalid_date': doc['observed_at'] = 'not a date'
        elif case == 'session_id': doc['session_id'] = ''
        elif case == 'missing': del doc['state']
        elif case == 'extra': doc['unexpected'] = True
        store.path.write_text(json.dumps(doc))
    assert store.read(NOW) is None
    with pytest.raises(RuntimeError, match='session_context_unavailable'):
        store(NOW)


def safe_observation(now):
    return GuardianObservation(**{k: GuardianEvidence(v, 'explicit-test', 'OBSERVATION', now)
        for k, v in dict(rain_active=False, rain_eta_minutes=None, wind_kmh=0,
                        gust_kmh=0, humidity_percent=40, dew_spread_c=10).items()})


@pytest.mark.parametrize('state', [State.ACTIVE, State.INACTIVE])
def test_loss_cannot_improve_decision(tmp_path, state):
    store = GuardianSessionStore(tmp_path / 'session.json')
    store.write(attestation(state))
    runner = GuardianPeriodicRunner(evidence_provider=safe_observation,
        session_context_provider=store, guardian_runner=GuardianRunner())
    valid = runner.run_cycle(logical_time=NOW)
    assert valid.assessment.session_state is state
    assert valid.decision_eligible
    for loss in ('expired', 'corrupt', 'missing'):
        time = NOW + timedelta(seconds=901) if loss == 'expired' else NOW
        if loss == 'corrupt': store.path.write_text('{')
        if loss == 'missing': store.path.unlink()
        result = runner.run_cycle(logical_time=time)
        assert result.errors == ('session_provider_error',)
        assert result.assessment.session_state is State.UNKNOWN
        assert result.assessment.action_applicability.value == 'UNKNOWN'
        assert result.assessment.risk_level == valid.assessment.risk_level
        assert result.recommended_action >= valid.recommended_action
        assert result.recommended_action.name == 'EMERGENCY_STOP'
        assert not result.decision_eligible
        assert result.assessment.hardware_action is None


def test_failed_atomic_replace_preserves_previous(tmp_path, monkeypatch):
    import astropilot.guardian_session_store as module
    store = GuardianSessionStore(tmp_path / 'session.json')
    store.write(attestation())
    def fail(*args): raise OSError('replace failed')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError): store.write(attestation(State.INACTIVE))
    assert store(NOW).state is State.ACTIVE
    assert list(tmp_path.iterdir()) == [store.path]


@pytest.mark.parametrize('invalid', [None, attestation(stamp=NOW.replace(tzinfo=None)),
    GuardianLiveSessionEvidence('ACTIVE', NOW, 'caller_session_heartbeat_v1', 'CALLER_ASSERTED'),
    GuardianLiveSessionEvidence(State.ACTIVE, NOW, 'inferred', 'CALLER_ASSERTED')])
def test_invalid_writer_does_not_replace(tmp_path, invalid):
    store = GuardianSessionStore(tmp_path / 'session.json')
    store.write(attestation())
    with pytest.raises(ValueError): store.write(invalid)
    assert store(NOW) == attestation()


def config(tmp_path, session):
    doc = dict(schema_version=1, interval_seconds=60, anchor=NOW.isoformat(), enabled=True,
               provider='open_meteo_current_v1', weather_site=dict(latitude=46, longitude=7, timeout_seconds=2))
    if session != 'omitted': doc['session_context'] = session
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(doc))
    return path


@pytest.mark.parametrize('session', [None, {}, {'provider': PROVIDER_ID, 'path': 'relative.json'},
    {'provider': 'inferred', 'path': '/tmp/session.json'},
    {'provider': PROVIDER_ID, 'path': '/tmp/session.json', 'extra': True}])
def test_host_config_strict(tmp_path, session):
    with pytest.raises(ValueError, match='config_invalid'): load_config(config(tmp_path, session))


@pytest.mark.parametrize('state', [State.ACTIVE, State.INACTIVE, None])
def test_host_coexists_with_builtin_live_weather(tmp_path, capsys, monkeypatch, state):
    from astropilot import guardian_live_evidence as live
    calls = []
    monkeypatch.setattr(live.ProductionGuardianWeatherAdapter, '__call__',
        lambda self, time: calls.append(time) or safe_observation(time))
    session_path = tmp_path / 'session.json'
    if state is not None: GuardianSessionStore(session_path).write(attestation(state))
    path = config(tmp_path, dict(provider=PROVIDER_ID, path=str(session_path)))
    code = main(['--config', str(path), '--data-dir', str(tmp_path / 'host'), '--once'], clock=lambda: NOW)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    cycle = events[1]
    assert calls == [NOW]
    assert code == (6 if state is None else 0)
    assert cycle['session_state'] == ('UNKNOWN' if state is None else state.value)
    assert cycle['decision_eligible'] is (state is not None)
    assert cycle['action'] == ('EMERGENCY_STOP' if state is None else 'CONTINUE')
    assert cycle['session_applicability'] == ('UNKNOWN' if state is None else
        'APPLICABLE' if state is State.ACTIVE else 'NOT_APPLICABLE')
    assert not any(event['event'] == 'notification' for event in events)


def test_omitted_config_preserves_injected_session(tmp_path, capsys):
    from astropilot.guardian_host import GuardianHostProviders
    path = config(tmp_path, 'omitted')
    assert load_config(path).session_context is None
    code = main(['--config', str(path), '--data-dir', str(tmp_path / 'host'), '--once'],
        provider_factories={'open_meteo_current_v1': lambda:
            GuardianHostProviders(safe_observation, lambda _: attestation())}, clock=lambda: NOW)
    assert code == 0
    assert json.loads(capsys.readouterr().out.splitlines()[1])['session_state'] == 'ACTIVE'


def test_unreadable_is_unknown(tmp_path, monkeypatch):
    store = GuardianSessionStore(tmp_path / 'session.json')
    store.write(attestation())
    def denied(*args, **kwargs): raise PermissionError('private path')
    monkeypatch.setattr(type(store.path), 'open', denied)
    assert store.read(NOW) is None
    with pytest.raises(RuntimeError, match='session_context_unavailable'):
        store(NOW)


def test_disabled_opt_in_never_reads_or_acquires(tmp_path, monkeypatch, capsys):
    path = config(tmp_path, dict(provider=PROVIDER_ID, path=str(tmp_path / 'absent.json')))
    doc = json.loads(path.read_text())
    doc['enabled'] = False
    path.write_text(json.dumps(doc))
    def forbidden(*args): pytest.fail('disabled host accessed session')
    monkeypatch.setattr(GuardianSessionStore, '__call__', forbidden)
    assert main(['--config', str(path), '--data-dir', str(tmp_path / 'unused'), '--once']) == 0
    assert not (tmp_path / 'unused').exists()
