"""Regression evidence for the persistent-collection READ-ONLY findings."""
from dataclasses import replace
from datetime import timedelta, datetime, timezone
import builtins
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from test_reference_station_lab import lab, run, observations, T, STATION, fake_snapshot
from astropilot.reference_station_lab import ObservationIndex, ReferenceLab, capture_forecast, canonical_utc
from astropilot.field_lab_collection import initialize, status, periodic_report, check_capacity, usage
from astropilot.field_lab_store import FieldLabArtifact


def test_index_single_pass_unrelated_observations():
    sample = observations()[0]
    for n in (10_000, 100_000):
        index = ObservationIndex(replace(sample, station_id='CDF',
            observed_at_utc=canonical_utc(T-timedelta(minutes=i))) for i in range(n))
        before = index.candidate_visits
        for i in range(200):
            assert index.nearest('NEU', sample.variable, T+timedelta(minutes=i)) == []
        assert index.revision_visits == n
        assert index.candidate_visits == before
        for i in range(200):
            index.nearest('CDF', sample.variable, T-timedelta(minutes=i))
        assert index.candidate_visits <= 400


def test_incremental_revision_a_b_a_and_last_computation(lab, monkeypatch):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    a = next(o for o in observations() if o.variable == 'temperature_2m' and o.value is not None)
    lab.save_observation(a)
    first = lab.comparisons(clock=lambda:T+timedelta(hours=2), persist=True, incremental=True)
    assert len(first) == 3
    with monkeypatch.context() as patch:
        patch.setattr(lab, 'durable_seal', lambda r:pytest.fail('unchanged run decoded'))
        assert lab.comparisons(clock=lambda:T+timedelta(hours=3), persist=True, incremental=True) == ()
    b = replace(a, value=a.value+1, retrieved_at_utc=canonical_utc(T+timedelta(hours=3)))
    lab.save_observation(b)
    second = lab.comparisons(clock=lambda:T+timedelta(hours=4), persist=True, incremental=True)
    assert len(second) == 1 and second[0].variable == 'temperature_2m'
    lab.save_observation(replace(a, retrieved_at_utc=canonical_utc(T+timedelta(hours=5))))
    third = lab.comparisons(clock=lambda:T+timedelta(hours=6), persist=True, incremental=True)
    assert len(third) == 1 and third[0].signed_error == first[0].signed_error
    assert status(lab)['last_comparison'] == canonical_utc(T+timedelta(hours=6))
    assert third[0].forecast_point_at_utc == first[0].forecast_point_at_utc
    rows = periodic_report(lab, '24h', clock=lambda:T+timedelta(hours=6))
    temperature = next(r for r in rows if r['station'] == 'NEU' and r['variable'] == 'temperature_2m')
    assert temperature['mean_bias'] == third[0].signed_error


def test_thousands_artifacts_status_and_short_report_payload_reads(lab, monkeypatch):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    for o in observations():
        lab.save_observation(o)
    lab.comparisons(clock=lambda:T+timedelta(hours=2), persist=True, incremental=True)
    with lab.store.writer_lock(max_names=lab.max_artifacts):
        for i in range(10_000):
            lab.save('synthetic', 'large-'+str(i), {'padding':'x'*2048}, T-timedelta(days=40))
    original = FieldLabArtifact.decode.__func__
    decoded = []
    def spy(cls, document):
        artifact = original(cls, document)
        decoded.append(artifact.artifact_type)
        return artifact
    monkeypatch.setattr(FieldLabArtifact, 'decode', classmethod(spy))
    assert status(lab)['usage']['count'] >= 10_000
    assert decoded == []
    monkeypatch.setattr(lab, 'comparisons', lambda **kw:pytest.fail('persisted report reconstructed'))
    assert periodic_report(lab, '24h', clock=lambda:T+timedelta(hours=2))
    assert 'synthetic' not in decoded and 'reference_acquisition' not in decoded
    assert len(decoded) <= 10
    assert list(lab.facts(artifact_type='reference_acquisition', station_id='CDF', stream=True)) == []


def test_report_guard_before_payload_decode(lab, monkeypatch):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    import astropilot.field_lab_collection as collection
    monkeypatch.setattr(collection, 'REPORT_LIMIT', 2)
    monkeypatch.setattr(FieldLabArtifact, 'decode', classmethod(lambda *a:pytest.fail('payload decoded before report limit')))
    with pytest.raises(ValueError, match='report_operational_limit'):
        periodic_report(lab, 'all', clock=lambda:T+timedelta(hours=2))


def _writer(root, user, start, results, label):
    os.environ['FIELD_LAB_DATA_DIR'] = root
    os.environ['ASTROPILOT_DATA_DIR'] = user
    lab = ReferenceLab(max_artifacts=10)
    start.wait(5)
    for attempt in range(100):
        try:
            with lab.store.writer_lock(max_names=10):
                check_capacity(lab, reserve=2)
                time.sleep(.05)
                for i in range(2):
                    lab.save('test', label+str(i), {'i':i}, T)
                results.put('written')
                return
        except RuntimeError as error:
            if 'writer_busy' not in str(error):
                results.put(str(error)); return
            time.sleep(.01)
        except ValueError as error:
            results.put(str(error)); return
    results.put('timeout')


def test_two_process_writers_recheck_budget_under_global_lock(lab, tmp_path):
    initialize()
    for i in range(6):
        lab.save('test', 'seed'+str(i), {'i':i}, T)
    context = multiprocessing.get_context('spawn')
    start, results = context.Event(), context.Queue()
    workers = [context.Process(target=_writer, args=(str(tmp_path/'lab'), str(tmp_path/'user'), start, results, name))
               for name in ('a', 'b')]
    for worker in workers:
        worker.start()
    start.set()
    outcomes = [results.get(timeout=15) for _ in workers]
    for worker in workers:
        worker.join(5)
        assert worker.exitcode == 0
    assert sorted(outcomes) == ['field_lab_capacity_stop_scientific_facts_preserved', 'written']
    assert usage(lab)['count'] == 8


def test_shared_lock_store_instances_and_symlink(lab, tmp_path):
    initialize()
    with lab.store.writer_lock():
        other = ReferenceLab()
        other.save('test', 'nested', {'ok':True}, T)
    path = tmp_path/'lab'/'.writer.lock'
    path.unlink()
    path.symlink_to(tmp_path/'user')
    with pytest.raises(OSError):
        lab.save('test', 'bad', {}, T)
    assert not (tmp_path/'user').exists()


def test_init_explicit_scheduler_and_runner(lab, tmp_path):
    from astropilot.field_lab_collection import scheduler, scheduled_main
    for operation in (lambda:scheduler('install'), scheduled_main):
        with pytest.raises((ValueError, FileNotFoundError)):
            operation()
    assert not (tmp_path/'lab').exists()


def test_capacity_status_and_cycle_entry_agree(lab):
    for i in range(8):
        lab.save('test', str(i), {'i':i}, T)
    lab.max_artifacts = 10
    value = usage(lab)
    assert value['blocked'] and value['warning'] and value['reserved_budget'] == 1
    assert value['effective_stop_at'] == 8 and value['remaining'] == 0
    with pytest.raises(ValueError, match='capacity_stop'):
        check_capacity(lab)


def test_missing_fcntl_import_cli_help_and_stable_commands(tmp_path):
    script = '''import builtins, sys
original = builtins.__import__
def missing(name, *args, **kw):
    if name == 'fcntl' and args and args[0].get('__name__') in ('astropilot.field_lab_store', 'astropilot.field_lab_collection'):
        raise ImportError('simulated Windows')
    return original(name, *args, **kw)
builtins.__import__ = missing
from astropilot.reference_station_cli import main
try: main(['--help'])
except SystemExit as error: assert error.code == 0
assert main(['scheduler', 'status']) == 0
assert main(['status']) == 0
for argv in (['init'], ['scheduler', 'install'], ['cycle'], ['stations', 'sync'], ['compare']):
    assert main(argv) == 2
'''
    env = dict(os.environ, FIELD_LAB_DATA_DIR=str(tmp_path/'lab'), ASTROPILOT_DATA_DIR=str(tmp_path/'user'))
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'ModuleNotFoundError' not in result.stderr
    assert result.stderr.count('field_lab_secure_lock_unavailable') == 5
    assert not (tmp_path/'lab').exists()


def test_non_posix_capability_fails_closed(lab, monkeypatch, capsys):
    import astropilot.field_lab_store as store
    from astropilot.reference_station_cli import main
    monkeypatch.setattr(store.os, 'supports_dir_fd', set())
    assert main(['status']) == 2
    assert 'field_lab_secure_storage_unavailable' in capsys.readouterr().err


def test_year_boundary_current_year_targets_continue(lab):
    created = datetime(2026, 12, 31, 22, tzinfo=timezone.utc)
    targets = [created+timedelta(hours=1), created+timedelta(hours=3)]
    snapshot = fake_snapshot()
    snapshot.retrieved_at_utc = created
    snapshot.payload['hourly']['time'] = [t.timestamp() for t in targets]
    forecast = capture_forecast(STATION, provider=lambda *a:snapshot, clock=lambda:created,
                                build=('a'*40, '1.0.0b7'))
    lab.save_run(forecast, clock=lambda:created+timedelta(minutes=1))
    observation = replace(observations()[0], observed_at_utc=canonical_utc(targets[1]),
                          retrieved_at_utc=canonical_utc(targets[1]+timedelta(hours=1)))
    calls = []
    client = SimpleNamespace(observations=lambda *args:calls.append(args) or [observation])
    assert lab.collect(client, clock=lambda:targets[1]+timedelta(hours=1), revision_days=7, coalesce=True) == 1
    assert calls == [('NEU', 'now')]
    assert lab.noncollectable_targets == [dict(station='NEU', target_at_utc=canonical_utc(targets[0]), reason='reference_cross_year_collection_not_supported')]


def test_unrelated_revision_does_not_recompute_targets(lab):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    for o in observations():
        lab.save_observation(o)
    lab.comparisons(clock=lambda:T+timedelta(hours=2), persist=True, incremental=True)
    a = observations()[0]
    for revision in (replace(a, station_id='CDF'),
                     replace(a, observed_at_utc=canonical_utc(T-timedelta(days=40)))):
        lab.save_observation(revision)
    assert lab.comparisons(clock=lambda:T+timedelta(hours=3), persist=True, incremental=True) == ()
    assert lab.computed_targets == 0


def test_index_nearest_tie_deterministic(lab):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    a = observations()[0]
    for stamp in (T-timedelta(minutes=10), T+timedelta(minutes=10)):
        lab.save_observation(replace(a, observed_at_utc=canonical_utc(stamp)))
    result = lab.comparisons(clock=lambda:T+timedelta(hours=2))
    assert result[0].reason == 'ambiguous_nearest_observation'
    assert result[0].signed_error is None


def test_all_cli_mutations_enter_shared_writer(lab, monkeypatch):
    import astropilot.reference_station_cli as cli
    from astropilot.field_lab_store import _WRITERS
    initialize()
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:lab)
    seen = []
    def execute(args, current):
        assert _WRITERS.state['identity'][1] == str(current.store._root)
        seen.append(args.command)
        return {}
    monkeypatch.setattr(cli, '_execute', execute)
    for argv in (['stations', 'sync'], ['forecast-run'], ['observations', 'collect'],
                 ['compare'], ['report', '--export'], ['cycle']):
        cli.execute(cli.parser().parse_args(argv))
    assert len(seen) == 6


def test_cli_report_uses_persisted_window(lab, monkeypatch):
    from astropilot.reference_station_cli import main
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    lab.comparisons(clock=lambda:T+timedelta(hours=2), persist=True, incremental=True)
    import astropilot.reference_station_cli as cli
    import astropilot.field_lab_collection as collection
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:lab)
    monkeypatch.setattr(lab, 'comparisons', lambda **kw:pytest.fail('unnecessary comparison'))
    # Default clock arguments are captured at definition; use the all window.
    assert main(['report', '--period', 'all']) == 0


def test_missing_metadata_fallback_and_symlink_refusal(lab, tmp_path):
    lab.save('test', 'legacy', {'ok':True}, T)
    name = lab.store._name('legacy')
    (tmp_path/'lab'/'metadata'/name).unlink()
    assert usage(lab)['count'] == 1
    (tmp_path/'lab'/'metadata').rmdir()
    (tmp_path/'lab'/'metadata').symlink_to(tmp_path/'user', target_is_directory=True)
    with pytest.raises(OSError):
        status(lab)



def test_legacy_comparison_does_not_claim_scientific_time_as_execution(lab):
    from dataclasses import asdict
    from astropilot.reference_station_lab import digest
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    comparison = lab.comparisons(clock=lambda:T+timedelta(hours=2))[0]
    payload = asdict(comparison)
    lab.save('reference_comparison', digest(payload), payload, T-timedelta(hours=1), 'NEU')
    value = status(lab)
    assert value['last_comparison'] is None and value['comparison_time_unavailable']


@pytest.mark.parametrize('count', [0, 2999, 3000, 11999, 12000, 14999, 15000])
def test_scheduler_capacity_boundaries_offline(lab, monkeypatch, count):
    import astropilot.field_lab_collection as collection
    from astropilot.field_lab_capacity import capacity_policy
    initialize()
    calls = []
    runner = lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=1 if argv[1] == 'print' else 0)
    monkeypatch.setattr(collection, 'launch_agents_path', lambda:collection.field_lab_root()/'mock-launch-agents'/'test.plist')
    collection.scheduler('install', runner=runner)
    monkeypatch.setattr(collection.sys, 'platform', 'darwin')
    # Synthetic metadata exercises exact admission counts without 15k disk writes.
    monkeypatch.setattr(lab.store.__class__, 'iter_metadata', lambda self, **kw:iter([
        dict(created_at_utc=canonical_utc(T), artifact_type='synthetic', time_max=canonical_utc(T))
    ] * count))
    policy = capacity_policy(collection.CAPACITY)
    assert policy == dict(operational_soft_limit=20000, stop_at=18000,
                          reserved_budget=3000, effective_stop_at=15000)
    value = status(lab)['usage']
    assert value['warning'] == (count >= 12000)
    assert value['blocked'] == value['would_block_next_cycle'] == (count >= 15000)
    if value['blocked']:
        with pytest.raises(ValueError, match='capacity_stop'):
            check_capacity(lab)
        with pytest.raises(ValueError, match='capacity_stop'):
            collection.scheduler('enable', runner=runner)
        assert calls == []
        assert not collection.launch_agents_path().exists()
    else:
        assert check_capacity(lab)['reserved_budget'] == 3000
        collection.scheduler('enable', runner=runner)
        assert any(argv[1] == 'bootstrap' for argv in calls)


@pytest.mark.parametrize('format', ['json', 'csv'])
def test_compare_export_full_active_state_idempotent(lab, monkeypatch, capsys, format):
    import csv
    import io
    import astropilot.reference_station_cli as cli
    import astropilot.field_lab_collection as collection
    for station in (STATION,):
        forecast = capture_forecast(station, provider=lambda *a:fake_snapshot(),
            clock=lambda:T-timedelta(minutes=59), build=('a'*40, '1.0.0b7'))
        lab.save_run(forecast, clock=lambda:T-timedelta(minutes=58))
        for observation in observations():
            lab.save_observation(replace(observation, station_id=station.station_id))
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:lab)
    actual_compare = lab.comparisons
    computed = []
    current = T+timedelta(hours=6)
    def compare(**kwargs):
        assert kwargs['persist'] and kwargs['incremental']
        result = actual_compare(clock=lambda:current, **kwargs)
        computed.append(len(result))
        return result
    monkeypatch.setattr(lab, 'comparisons', compare)
    actual_report = collection.periodic_report
    monkeypatch.setattr(collection, 'periodic_report', lambda *a, **kw:
        actual_report(*a, clock=lambda:current, **kw))
    def invoke(argv):
        assert cli.main(argv+['--format', format]) == 0
        output = capsys.readouterr().out
        rows = json.loads(output) if format == 'json' else list(csv.DictReader(io.StringIO(output)))
        return output, rows
    first, rows = invoke(['compare', '--export'])
    assert len(rows) == 6 and computed == [3]
    report_output, _ = invoke(['report', '--period', 'all'])
    assert first == report_output
    # Unchanged inputs must not decode forecast seals or observations for a rebuild.
    with monkeypatch.context() as patch:
        patch.setattr(lab, 'durable_seal', lambda *a:pytest.fail('unchanged target recalculated'))
        rerun, _ = invoke(['compare', '--export'])
    assert rerun == first and computed == [3, 0]
    a = next(o for o in observations() if o.variable == 'temperature_2m' and o.value is not None)
    for station_id in ('NEU',):
        lab.save_observation(replace(a, station_id=station_id, value=a.value+2,
                                    retrieved_at_utc=canonical_utc(T+timedelta(hours=4))))
    current += timedelta(hours=1)
    revised, revised_rows = invoke(['compare', '--export'])
    assert len(revised_rows) == 6 and computed == [3, 0, 1]
    assert revised != first
    assert [r for r in revised_rows if r['variable'] == 'relative_humidity_2m'] == [
        r for r in rows if r['variable'] == 'relative_humidity_2m']
    full, _ = invoke(['report', '--period', 'all'])
    assert revised == full
    assert invoke(['compare', '--export'])[0] == revised
    assert computed == [3, 0, 1, 0]
    persisted = [json.loads(a.payload_json)['rows'] for a in
                 lab.store.iter_artifacts(artifact_type='reference_report')]
    assert len(persisted) == 2  # Identical exports deduplicate, revised export remains complete.
    assert all(len(rows) == 6 for rows in persisted)
