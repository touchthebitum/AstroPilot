from datetime import datetime, timedelta, timezone
import json
import pytest
from astropilot.opportunity_alert_status import StatusObserver, read_status

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def observer(tmp_path, clock=lambda: NOW):
    return StatusObserver(tmp_path, clock=clock)


def startup(obs, enabled=True, channel='windows'):
    obs.start(enabled=enabled, channel=channel, interval_seconds=60)


def success(obs):
    obs.record(dict(event='cycle', status='COMPLETED', cycle_status='NO_ALERT',
                    logical_time=NOW.isoformat(), slot=NOW.isoformat(), reason='cycle_completed'))


def test_missing_is_unknown_and_read_does_not_create(tmp_path):
    root = tmp_path / 'absent'
    assert read_status(root, now=NOW)['state'] == 'unknown'
    assert not root.exists()


def test_success_delivery_shutdown_and_restart_history(tmp_path):
    obs = observer(tmp_path)
    startup(obs)
    success(obs)
    obs.record(dict(event='notification', status='DELIVERED', reason='accepted_by_os'))
    obs.record(dict(event='shutdown'))
    state = read_status(tmp_path, now=NOW)
    assert state['state'] == 'stopped'
    assert state['last_success_at'] == NOW.isoformat()
    assert state['notification']['status'] == 'DELIVERED'
    restarted = observer(tmp_path)
    startup(restarted, False, 'disabled')
    state = read_status(tmp_path, now=NOW)
    assert state['state'] == 'recent_activity'
    assert state['enabled'] is False and state['channel'] == 'disabled'
    assert state['notification']['status'] == 'DELIVERED'
    assert state['last_success_at'] == NOW.isoformat()


def test_cycle_error_not_success_and_skip_not_recovery(tmp_path):
    obs = observer(tmp_path)
    startup(obs)
    obs.record(dict(event='cycle', status='COMPLETED', cycle_status='ERROR', reason='cycle_completed'))
    obs.record(dict(event='cycle', status='SKIPPED', cycle_status=None, reason='slot_already_reserved'))
    state = read_status(tmp_path, now=NOW)
    assert state['last_success_at'] is None
    assert state['error'] == 'cycle_failed'
    success(obs)
    assert read_status(tmp_path, now=NOW)['error'] is None


def test_delivery_error_and_recovery(tmp_path):
    obs = observer(tmp_path)
    startup(obs)
    success(obs)
    obs.record(dict(event='notification', status='FAILED', reason='delivery_timeout'))
    assert read_status(tmp_path, now=NOW)['error'] == 'delivery_failed'
    obs.record(dict(event='notification', status='DELIVERED', reason='accepted_by_os'))
    assert read_status(tmp_path, now=NOW)['error'] is None


def test_stale_does_not_claim_running(tmp_path):
    obs = observer(tmp_path)
    startup(obs)
    assert read_status(tmp_path, now=NOW + timedelta(seconds=121))['state'] == 'stale'
    assert read_status(tmp_path, now=NOW - timedelta(seconds=1))['state'] == 'unavailable'


@pytest.mark.parametrize('content', ['{broken', '[]', '{"schema_version":true}', 'x' * 17000])
def test_invalid_bounded_state(tmp_path, content):
    (tmp_path / 'opportunity_alert_status.json').write_text(content)
    assert read_status(tmp_path, now=NOW)['state'] == 'unavailable'


def test_reader_private_fields_rejected_and_bytes_unchanged(tmp_path):
    obs = observer(tmp_path)
    startup(obs)
    path = tmp_path / 'opportunity_alert_status.json'
    before = path.read_bytes()
    result = read_status(tmp_path, now=NOW)
    assert path.read_bytes() == before
    assert 'data_dir' not in result and 'pid' not in result
    doc = json.loads(before)
    doc['secret'] = 'private'
    path.write_text(json.dumps(doc))
    assert read_status(tmp_path, now=NOW)['state'] == 'unavailable'


def test_symlink_not_read_or_overwritten(tmp_path):
    other = tmp_path / 'private.json'
    other.write_text('private')
    path = tmp_path / 'opportunity_alert_status.json'
    try:
        path.symlink_to(other)
    except OSError:
        pytest.skip('symlink unavailable')
    assert read_status(tmp_path, now=NOW)['state'] == 'unavailable'
    startup(observer(tmp_path))
    assert other.read_text() == 'private' and path.is_symlink()


def test_publication_failure_is_nonfatal(tmp_path, monkeypatch):
    obs = observer(tmp_path)
    monkeypatch.setattr(obs, '_publish', lambda: (_ for _ in ()).throw(OSError('private detail')))
    startup(obs)
    success(obs)
    obs.record(dict(event='notification', status='DELIVERED', reason='accepted_by_os'))


def test_unicode_paths_and_lab_rejected(tmp_path):
    root = tmp_path / 'Franck Testé 空间'
    root.mkdir()
    startup(observer(root))
    assert read_status(root, now=NOW)['enabled'] is True
    (root / '.field_lab_namespace').write_text('{}')
    assert read_status(root, now=NOW)['state'] == 'unavailable'


def test_nonregular_document(tmp_path):
    (tmp_path / 'opportunity_alert_status.json').mkdir()
    assert read_status(tmp_path, now=NOW)['state'] == 'unavailable'


def test_fifo_never_blocks(tmp_path):
    import os
    if not hasattr(os, 'mkfifo'):
        pytest.skip('FIFO unsupported')
    os.mkfifo(tmp_path / 'opportunity_alert_status.json')
    assert read_status(tmp_path, now=NOW)['state'] == 'unavailable'


def test_host_main_publishes_without_changing_logs(tmp_path, monkeypatch, capsys):
    from astropilot.opportunity_alert_host import main
    monkeypatch.delenv('FIELD_LAB_DATA_DIR', raising=False)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(dict(schema_version=1, interval_seconds=60, policy={}, availability=None)))
    assert main(['--config', str(config), '--data-dir', str(tmp_path), '--once']) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e['event'] for e in events] == ['startup', 'cycle', 'shutdown']
    state = read_status(tmp_path)
    assert state['enabled'] is False and state['channel'] == 'disabled'
    assert state['last_success_at'] is not None and state['state'] == 'stopped'
    assert not (tmp_path / 'opportunity_alert_ledger.json').exists()


# The observer may fail, but a durably claimed alert must still be delivered once.
from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment


def test_observer_write_failure_never_suppresses_delivery(complete, policy, tmp_path, monkeypatch):
    from threading import Event
    from unittest.mock import Mock
    from test_opportunity_alert_notification_v1 import claimed
    from astropilot.opportunity_alert_host import OpportunityAlertHost
    from astropilot.opportunity_alert_scheduler import SchedulerResult, SchedulerStatus, SchedulerCadence
    from astropilot.opportunity_alert_notification import DeliveryResult, DeliveryStatus
    cycle, _ = claimed(complete, policy, tmp_path)
    ledger_path = tmp_path / 'opportunity_alert_ledger.json'
    ledger = ledger_path.read_bytes()
    obs = observer(tmp_path)
    monkeypatch.setattr(obs, '_publish', lambda: (_ for _ in ()).throw(OSError('no disk')))
    startup(obs)
    scheduler = Mock(cadence=SchedulerCadence())
    scheduler.poll.return_value = SchedulerResult(SchedulerStatus.COMPLETED, complete.timeline_start,
        'cycle_completed', cycle)
    notifier = Mock()
    notifier.notify.return_value = DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
    OpportunityAlertHost(scheduler=scheduler, policy=policy, clock=lambda: complete.timeline_start,
        stop_event=Event(), report=obs.record, notifier=notifier).run(once=True)
    notifier.notify.assert_called_once()
    assert ledger_path.read_bytes() == ledger
