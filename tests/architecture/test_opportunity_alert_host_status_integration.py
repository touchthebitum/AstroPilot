"""Exercise production CLI wiring, scheduler/runner/ledger, reader/API and UI.
Only external Tonight inputs, clock and OS delivery are substituted.
"""
from dataclasses import asdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import subprocess
import os
import sys
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment
from astropilot import opportunity_alert_host as host
from astropilot import opportunity_alert_status as status
from astropilot.app import create_app
from astropilot.opportunity_alert_notification import DeliveryResult, DeliveryStatus
from decision.services.tonight_application_service import TonightResult, TonightStatus


@pytest.fixture
def deployment(tmp_path, monkeypatch, complete, policy):
    monkeypatch.delenv('FIELD_LAB_DATA_DIR', raising=False)
    root = tmp_path / 'Franck Testé'
    root.mkdir()
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(root))
    at = complete.timeline_start
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at
    monkeypatch.setattr(host, 'datetime', Clock)
    monkeypatch.setattr(status, 'datetime', Clock)
    service = Mock()
    service.evaluate.return_value = complete
    monkeypatch.setattr(host, 'PreparingTonightService', lambda **kw: service)
    notifier = Mock()
    notifier.notify.return_value = DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
    monkeypatch.setattr(host, 'WindowsNotifier', lambda: notifier)
    snapshots = []
    save = status.StatusObserver._save
    def observe(obs):
        save(obs)
        snapshots.append(status.read_status(root, now=at))
    monkeypatch.setattr(status.StatusObserver, '_save', observe)
    config = tmp_path / 'host.json'
    def run(enabled=True):
        values = asdict(policy)
        values['enabled'] = enabled
        config.write_text(json.dumps(dict(schema_version=1, interval_seconds=60,
            policy=values, availability={'mode': 'all_night'} if enabled else None,
            notification_channel='windows')))
        return host.main(['--config', str(config), '--data-dir', str(root), '--once'])
    def api():
        def forbidden(*a, **kw):
            raise AssertionError('status GET invoked business operation')
        with TestClient(create_app(service_factory=forbidden, weather_provider=forbidden,
                profile_provider=forbidden, alert_ledger_factory=forbidden)) as client:
            before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            response = client.get('/v1/opportunity-alerts/status')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
            assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            return response.json()
    return root, run, api, service, notifier, snapshots, at


@pytest.mark.parametrize('delivery,reason', [('DELIVERED', 'accepted_by_os'),
    ('FAILED', 'delivery_timeout'), ('SKIPPED', 'unsupported_platform')])
def test_claim_delivery_api_and_restart_history(deployment, delivery, reason, capsys):
    root, run, api, service, notifier, snapshots, at = deployment
    notifier.notify.return_value = DeliveryResult(DeliveryStatus(delivery), reason)
    assert run() == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e['event'] for e in events] == ['startup', 'cycle', 'notification', 'shutdown']
    assert events[1]['cycle_status'] == 'ALERT_EMITTED'
    assert snapshots[0]['enabled'] and snapshots[0]['channel'] == 'windows'
    assert snapshots[0]['last_success_at'] is None
    assert snapshots[1]['state'] == 'recent_activity'
    assert snapshots[1]['last_success_at'] == at.isoformat()
    result = api()
    assert result == snapshots[-1]
    assert result['state'] == 'stopped'
    assert result['notification'] == dict(at=at.isoformat(), status=delivery, reason=reason)
    assert result['error'] == ('delivery_failed' if delivery == 'FAILED' else None)
    ledger = (root / 'opportunity_alert_ledger.json').read_bytes()
    assert ledger
    service.evaluate.assert_called_once()
    notifier.notify.assert_called_once()
    # The reserved slot on restart produces no new delivery and retains history.
    assert run() == 0
    assert api()['notification'] == result['notification']
    assert api()['last_success_at'] == result['last_success_at']
    assert (root / 'opportunity_alert_ledger.json').read_bytes() == ledger
    notifier.notify.assert_called_once()
    assert status.read_status(root, now=at + timedelta(seconds=121))['state'] == 'stale'
    assert 'state' not in json.loads((root / status.FILENAME).read_text())


@pytest.mark.parametrize('enabled', [False, True])
def test_no_alert_without_invented_notification(deployment, enabled):
    root, run, api, service, notifier, snapshots, at = deployment
    service.evaluate.return_value = TonightResult(None, None, None, status=TonightStatus.NO_NIGHT)
    assert run(enabled) == 0
    result = api()
    assert result['enabled'] is enabled
    assert result['channel'] == 'windows'
    assert result['last_success_at'] == at.isoformat()
    assert result['notification'] is None
    assert result['error'] is None
    notifier.notify.assert_not_called()
    if enabled:
        service.evaluate.assert_called_once()
    else:
        service.evaluate.assert_not_called()
        assert not (root / 'opportunity_alert_ledger.json').exists()


@pytest.mark.parametrize('cycle_error', [True, False])
def test_next_cycle_retains_history_and_exit_code(deployment, cycle_error):
    root, run, api, service, notifier, snapshots, at = deployment
    assert run() == 0
    previous = api()
    # Use a dedicated new scheduler directory to exercise an error on the next run.
    shutil.rmtree(root / 'opportunity_alert_scheduler')
    if cycle_error:
        service.evaluate.side_effect = RuntimeError('private weather details')
    else:
        service.evaluate.return_value = TonightResult(None, None, None, status=TonightStatus.NO_NIGHT)
    assert run() == int(cycle_error)
    result = api()
    assert result['error'] == ('cycle_failed' if cycle_error else None)
    assert result['last_success_at'] == previous['last_success_at']
    assert result['notification'] == previous['notification']
    assert 'private' not in json.dumps(result)
    notifier.notify.assert_called_once()


@pytest.mark.parametrize('cycle_error', [False, True])
def test_publication_failure_preserves_exit_and_delivery(deployment, monkeypatch, cycle_error, capsys):
    root, run, api, service, notifier, snapshots, at = deployment
    def unavailable(obs):
        raise OSError('private disk diagnostics')
    monkeypatch.setattr(status.StatusObserver, '_publish', unavailable)
    if cycle_error:
        service.evaluate.side_effect = RuntimeError('weather unavailable')
    assert run() == int(cycle_error)
    if cycle_error:
        notifier.notify.assert_not_called()
    else:
        notifier.notify.assert_called_once()
        assert (root / 'opportunity_alert_ledger.json').exists()
    assert api() == {'state': 'unknown'}
    errors = capsys.readouterr().err.splitlines()
    assert errors and set(errors) == {'opportunity_alert_status_unavailable'}


@pytest.mark.parametrize('case', ['disabled', 'running', 'no_alert', 'delivered',
                                 'failed', 'stale', 'cooperative_stop'])
def test_real_host_snapshot_api_ui(deployment, case, tmp_path, monkeypatch):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for UI execution')
    root, run, api, service, notifier, snapshots, at = deployment
    if case == 'failed':
        notifier.notify.return_value = DeliveryResult(DeliveryStatus.FAILED, 'delivery_timeout')
    if case == 'no_alert':
        service.evaluate.return_value = TonightResult(None, None, None, status=TonightStatus.NO_NIGHT)
    assert run(case != 'disabled') == 0
    if case == 'running':
        # Replay bytes actually published after the completed cycle, before shutdown.
        published = dict(snapshots[1])
        published.pop('state')
        (root / status.FILENAME).write_text(json.dumps(published))
    if case == 'stale':
        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return at + timedelta(seconds=121)
        monkeypatch.setattr(status, 'datetime', Later)
    payload = api()
    expected = dict(enabled='Désactivées' if case == 'disabled' else 'Activées',
        notification='Aucune notification enregistrée' if case in ('disabled', 'no_alert', 'running')
            else 'Échec de notification' if case == 'failed' else 'Acceptée par le système',
        summary='ancien' if case == 'stale' else 'activité récente' if case == 'running' else 'Arrêt enregistré',
        action='autorisations' if case == 'failed' else '')
    source = (Path(__file__).parents[2] / 'astropilot/web/alert-status.js').read_text()
    harness = r"""
const assert = require('node:assert/strict');
const elements = {};
for (const name of ['dialog','summary','details','note','action','enabled','channel','success','notification','updated','open','refresh','close']) {
 elements[name] = {textContent:'', hidden:false, open:false, listeners:{},
  addEventListener(name, fn) {this.listeners[name]=fn;},
  showModal() {this.open=true;}, close() {this.open=false;this.listeners.close();}};
}
const document = {querySelector: id => elements[id.replace('#alerts-status-','')]};
let calls=[];
const fetch = async (url, opts) => {
 calls.push([url,opts.method]);
 return {ok:true,json:async()=>payload};
};
"""
    checks = r"""
(async()=>{
 elements.open.listeners.click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(elements.details.hidden,false);
 assert.equal(elements.enabled.textContent, expected.enabled);
 for (const name of ['notification','summary','action'])
   assert(elements[name].textContent.includes(expected[name]), name+': '+elements[name].textContent);
 assert.equal(elements.channel.textContent,'Windows');
 assert.notEqual(elements.success.textContent,'Aucun relevé');
 assert.deepEqual(calls,[['/v1/opportunity-alerts/status','GET']]);
})().catch(error=>{console.error(error);process.exit(1);});
"""
    script = tmp_path / 'host-status-ui.cjs'
    script.write_text('const payload=' + json.dumps(payload) + ';\nconst expected='
        + json.dumps(expected) + ';\n' + harness + source + checks)
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_native_disabled_host_process_snapshot_api(tmp_path, monkeypatch):
    """No injected host dependencies, no service registration, no notification."""
    root = tmp_path / 'Franck Testé native'
    root.mkdir()
    config = tmp_path / 'disabled.json'
    config.write_text(json.dumps(dict(schema_version=1, interval_seconds=60,
        policy={}, availability=None, notification_channel='disabled')))
    env = dict(os.environ, ASTROPILOT_DATA_DIR=str(root))
    env.pop('FIELD_LAB_DATA_DIR', None)
    result = subprocess.run([sys.executable, '-m', 'astropilot.opportunity_alert_host',
        '--config', str(config), '--data-dir', str(root), '--once'],
        capture_output=True, text=True, timeout=20, env=env)
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [e['event'] for e in events] == ['startup', 'cycle', 'shutdown']
    assert events[1]['cycle_status'] == 'NO_ALERT'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(root))
    monkeypatch.delenv('FIELD_LAB_DATA_DIR', raising=False)
    with TestClient(create_app(service_factory=lambda: None)) as client:
        observed = client.get('/v1/opportunity-alerts/status').json()
    assert observed['state'] == 'stopped'
    assert observed['enabled'] is False and observed['channel'] == 'disabled'
    assert observed['last_success_at'] is not None
    assert observed['notification'] is None
    assert not (root / 'opportunity_alert_ledger.json').exists()
