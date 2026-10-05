"""Opt-in local collection. No application factory or user persistence APIs."""
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta
from dataclasses import asdict
try:
    import fcntl
except ImportError:
    fcntl = None
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import logging
import stat

from astropilot.field_lab_paths import field_lab_root
from astropilot.reference_station_lab import (ReferenceLab, MeteoSwissReferenceClient,
    capture_forecast, select_stations, now_utc, utc, digest, report)

CAPACITY = 2_000_000  # Hard enumeration safety ceiling, not an operating promise.
from astropilot.field_lab_capacity import (
    OPERATIONAL_SOFT_LIMIT, RESERVED_BUDGET, WARNING, STOP, capacity_policy)
REPORT_LIMIT = 20_000
REVISION_DAYS = 7
LABEL = 'org.nightmerit.field-lab'


def proposed_root():
    return Path.home() / 'Documents' / 'NightMerit Field Lab' / 'reference-weather-v1'


def require_initialized(lab):
    try:
        with lab.store._directory(root_only=True):
            pass
    except FileNotFoundError as error:
        raise ValueError('field_lab_init_required') from error


def initialize():
    store = ReferenceLab(max_artifacts=CAPACITY).store
    with store.writer_lock(create=True, max_names=CAPACITY):
        pass
    return {'root': str(field_lab_root()), 'initialized': True, 'smoke_imported': False}


def artifacts(lab, artifact_type=None):
    return lab.store.iter_artifacts(max_names=lab.max_artifacts, artifact_type=artifact_type)


def usage(lab, *, clock=now_utc):
    current = utc(clock())
    count, recent, size = 0, 0, 0
    kinds = Counter()
    oldest = newest = None
    for meta in lab.store.iter_metadata(max_names=lab.max_artifacts):
        stamp = utc(meta['created_at_utc'])
        count += 1
        kinds[meta['artifact_type']] += 1
        recent += current-timedelta(days=7) <= stamp <= current
        oldest = min(oldest, stamp) if oldest else stamp
        newest = max(newest, stamp) if newest else stamp
    def directory_bytes(path):
        total = 0
        with os.scandir(path) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
                elif stat.S_ISDIR(info.st_mode):
                    total += directory_bytes(entry.path)
        return total
    if field_lab_root().exists():
        size = directory_bytes(field_lab_root())
    policy = capacity_policy(lab.max_artifacts)
    stop_at = policy['stop_at']
    reserve = policy['reserved_budget']
    effective = policy['effective_stop_at']
    rate = recent/7
    return dict(count=count, by_type=dict(sorted(kinds.items())), capacity=lab.max_artifacts,
                operational_soft_limit=policy['operational_soft_limit'],
                remaining=max(0, stop_at-count-1), reserved_budget=reserve, effective_stop_at=effective,
                growth_per_day_7d=rate, estimated_days_to_stop=(effective-count)/rate if rate else None,
                oldest=oldest.isoformat() if oldest else None, newest=newest.isoformat() if newest else None,
                disk_bytes=size, warning=count >= effective*WARNING,
                blocked=count >= effective, would_block_next_cycle=count >= effective)


def check_capacity(lab, reserve=None):
    result = usage(lab)
    if reserve is None:
        reserve = result['reserved_budget']
    stop_at = capacity_policy(lab.max_artifacts)['stop_at']
    if result['count'] + reserve >= stop_at:
        raise ValueError('field_lab_capacity_stop_scientific_facts_preserved')
    return result


@contextmanager
def cycle_lock(lab):
    require_initialized(lab)
    with lab.store.writer_lock(max_names=lab.max_artifacts):
        yield


def periodic_report(lab, period='all', *, clock=now_utc, tolerance_minutes=10, historical=False):
    days = {'24h': 1, '7d': 7, '30d': 30, 'all': None}[period]
    current = utc(clock())
    start = (current-timedelta(days=days)).isoformat(timespec='microseconds') if days else None
    end = current.isoformat(timespec='microseconds')
    # Exact percentiles retain values: explicitly bound this materialization.
    count = sum(1 for m in lab.store.iter_metadata(max_names=lab.max_artifacts)
                if m['artifact_type'] in ('reference_comparison', 'reference_comparison_state')
                and (start is None or m['time_max'] >= start) and m['time_min'] <= end)
    if count > REPORT_LIMIT:
        raise ValueError('field_lab_report_operational_limit_exceeded_use_shorter_period')
    states = lab.comparison_states(start=start, end=end, tolerance_minutes=tolerance_minutes, historical=historical)
    comparisons = tuple(value[1] for value in states.values())
    if not comparisons:
        targets = sum(m['point_count']*3 for m in lab.store.iter_metadata(max_names=lab.max_artifacts)
                      if m['artifact_type'] == 'reference_forecast' and
                      (start is None or m['time_max'] >= start) and m['time_min'] <= end)
        if targets > REPORT_LIMIT:
            raise ValueError('field_lab_report_operational_limit_exceeded_use_shorter_period')
        # Read-only compatibility reconstruction, filtered at the target boundary.
        comparisons = lab.comparisons(clock=clock, tolerance_minutes=tolerance_minutes,
                                      historical=historical, start=start, end=end)
        if len(comparisons) > REPORT_LIMIT:
            raise ValueError('field_lab_report_operational_limit_exceeded_use_shorter_period')
    run_ids = {c.forecast_run_id for c in comparisons}
    from astropilot.reference_station_lab import ReferenceForecastRun
    runs = (ReferenceForecastRun(**json.loads(lab.store.load(idempotency_key=key).payload_json)) for key in run_ids)
    return report(comparisons, runs)


def cycle(lab, *, clock=now_utc, client=None, capture=capture_forecast, tolerance_minutes=10, dry_run=False):
    from astropilot.reference_station_cli import saved_catalogue
    from astropilot.reference_station_lab import validate_tolerance
    validate_tolerance(tolerance_minutes)
    current = utc(clock())
    items = tuple(artifacts(lab, ('catalog_activation_event', 'collection_success')))
    activations = [a for a in items if a.artifact_type == 'catalog_activation_event']
    sync_due = not activations or current-max(utc(a.created_at_utc) for a in activations) >= timedelta(days=7)
    runs = tuple(lab.iter_facts(artifact_type='reference_forecast', start=(current-timedelta(hours=12)).isoformat()))
    plan = dict(catalogue_due=sync_due, forecast_interval_hours=12, horizon_hours=24,
                revision_horizon_days=REVISION_DAYS, dry_run=dry_run)
    if dry_run:
        return dict(plan, writes=0, network_calls=0)
    with cycle_lock(lab):
        # Re-read after locking: another cycle may have completed while planning.
        items = tuple(artifacts(lab, ('catalog_activation_event', 'collection_success')))
        successes = [a for a in items if a.artifact_type == 'collection_success']
        if successes and current-max(utc(a.created_at_utc) for a in successes) < timedelta(hours=1):
            return dict(plan, no_op=True, writes=0, network_calls=0)
        capacity = check_capacity(lab)
        lab.write_budget = capacity['remaining']
        runs = tuple(lab.iter_facts(artifact_type='reference_forecast', start=(current-timedelta(hours=12)).isoformat()))
        client = client or MeteoSwissReferenceClient()
        if isinstance(client, MeteoSwissReferenceClient):
            client.asset_audit_sink = lambda payload:save_asset_audit(lab, payload)
        activations = [a for a in items if a.artifact_type == "catalog_activation_event"]
        sync_due = not activations or current-max(utc(a.created_at_utc) for a in activations) >= timedelta(days=7)
        if sync_due:
            catalogue = client.stations()
            # Preserve explicitly selected IDs across metadata refreshes.
            ids = saved_catalogue(lab)[1] if activations else None
            stations = select_stations(catalogue, ids)
            payload = dict(schema_version=1, source='MeteoSwiss', collection='ch.meteoschweiz.ogd-smn',
                           stations=[asdict(s) for s in catalogue], active_station_ids=[s.station_id for s in stations],
                           selection_version='smn-prospective-v1')
            lab.save_catalogue(payload, current.isoformat())
        catalogue, active = saved_catalogue(lab)
        created = 0
        for station in select_stations(catalogue, active):
            latest = [utc(r.forecast_retrieved_at_utc) for r in runs if r.prospective and r.station_id == station.station_id]
            if not latest or current-max(latest) >= timedelta(hours=12):
                lab.save_run(capture(station, hours=24), clock=clock)
                created += 1
        collected = lab.collect(client, clock=clock, tolerance_minutes=tolerance_minutes,
                                revision_days=REVISION_DAYS, coalesce=True)
        lab.comparisons(clock=clock, tolerance_minutes=tolerance_minutes, persist=True, incremental=True)
        rows = periodic_report(lab, '24h', clock=clock, tolerance_minutes=tolerance_minutes)
        payload = {'schema_version': 1, 'rows': rows}
        lab.save('reference_report', digest(payload), payload, current.isoformat())
        # Success is coalesced by UTC hour, keeping operational evidence bounded.
        stamp = current.replace(minute=0, second=0, microsecond=0).isoformat()
        lab.save('collection_success', 'success-'+digest(stamp), {'at_utc': stamp, 'completed_at_utc': utc(clock()).isoformat()}, stamp)
        return dict(plan, forecasts_created=created, acquisitions_created=collected,
                    noncollectable_targets=lab.noncollectable_targets, rows=rows, usage=usage(lab, clock=clock))


from astropilot.reference_station_lab import writer_method


@writer_method
def save_asset_audit(lab, payload):
    maximum, hashes = None, set()
    for artifact in lab.store.iter_artifacts(max_names=lab.max_artifacts,
            artifact_type='official_asset_activation', station_id=payload['station']):
        previous = json.loads(artifact.payload_json)
        if previous['asset_href'] != payload['asset_href']:
            continue
        stamp = utc(previous['retrieved_at_utc'])
        if maximum is None or stamp > maximum:
            maximum, hashes = stamp, {previous['sha256']}
        elif stamp == maximum:
            hashes.add(previous['sha256'])
    if len(hashes) > 1:
        raise ValueError('field_lab_asset_activation_ambiguous')
    if hashes == {payload['sha256']}:
        return False
    return lab.save('official_asset_activation', 'asset-'+digest(payload), payload,
                    payload['retrieved_at_utc'], payload['station'])


def scheduler_path():
    return field_lab_root() / 'scheduler.plist'


def launch_agents_path():
    return Path.home() / 'Library' / 'LaunchAgents' / (LABEL+'.plist')


def scheduler_document():
    root = field_lab_root()
    return dict(Label=LABEL, ProgramArguments=[sys.executable, '-m', 'astropilot.field_lab_collection'],
                WorkingDirectory=str(Path(__file__).resolve().parent.parent),
                EnvironmentVariables={'FIELD_LAB_DATA_DIR': str(root),
                                      'ASTROPILOT_DATA_DIR': str(__import__('astropilot.user_profile', fromlist=['get_user_data_dir']).get_user_data_dir())},
                StartInterval=3600, RunAtLoad=False, ProcessType='Background')


def scheduler(operation, *, runner=subprocess.run):
    if operation == 'status':
        return _scheduler(operation, runner=runner)
    if fcntl is None or os.name != 'posix':
        raise RuntimeError('field_lab_secure_lock_unavailable')
    lab = ReferenceLab()
    require_initialized(lab)
    with lab.store.writer_lock(max_names=CAPACITY):
        return _scheduler(operation, runner=runner)


def _scheduler(operation, *, runner=subprocess.run):
    path = scheduler_path()
    domain = 'gui/'+str(os.getuid()) if hasattr(os, 'getuid') else None
    if operation == 'status':
        result = {'installed': path.exists(), 'plist': str(path), 'enabled': False}
        if path.exists() and sys.platform == 'darwin':
            result['enabled'] = runner(['launchctl', 'print', domain+'/'+LABEL], capture_output=True).returncode == 0
        return result
    if operation == 'install':
        if fcntl is None or os.name != 'posix':
            raise RuntimeError('field_lab_secure_lock_unavailable')
        with ReferenceLab().store._directory(root_only=True):
            pass
        document = plistlib.dumps(scheduler_document(), sort_keys=True).decode()
        store = ReferenceLab().store
        # Scheduler plans are immutable; uninstall before changing interpreter/configuration.
        with store._directory(root_only=True) as fd:
            store._publish(fd, 'scheduler.plist', document)
        return {'installed': True, 'enabled': False, 'plist': str(path)}
    if operation == 'enable':
        if sys.platform != 'darwin':
            raise RuntimeError('field_lab_scheduler_requires_macos')
        check_capacity(ReferenceLab(max_artifacts=CAPACITY))
        with ReferenceLab().store._directory(root_only=True) as fd:
            if plistlib.loads(ReferenceLab().store._read(fd, 'scheduler.plist').encode()) != scheduler_document():
                raise ValueError('field_lab_scheduler_plan_mismatch')
        login_path = launch_agents_path()
        login_path.parent.mkdir(parents=True, exist_ok=True)
        parent_fd = os.open(login_path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        published = False
        try:
            published = ReferenceLab().store._publish(parent_fd, login_path.name, plistlib.dumps(scheduler_document(), sort_keys=True).decode())
            if not scheduler('status', runner=runner)['enabled']:
                runner(['launchctl', 'bootstrap', domain, str(login_path)], check=True)
        except BaseException:
            if published:
                os.unlink(login_path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            raise
        finally:
            os.close(parent_fd)
    elif operation in ('disable', 'uninstall'):
        state = scheduler('status', runner=runner)
        if state['enabled']:
            runner(['launchctl', 'bootout', domain+'/'+LABEL], check=True)
        login_path = launch_agents_path()
        if login_path.exists() or login_path.is_symlink():
            parent_fd = os.open(login_path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                document = ReferenceLab().store._read(parent_fd, login_path.name)
                if plistlib.loads(document.encode()).get('Label') != LABEL:
                    raise ValueError('field_lab_scheduler_label_mismatch')
                os.unlink(login_path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        if operation == 'uninstall' and path.exists():
            with ReferenceLab().store._directory(root_only=True) as fd:
                os.unlink('scheduler.plist', dir_fd=fd)
                os.fsync(fd)
    return scheduler('status', runner=runner)


def status(lab):
    latest = {}
    last_observed = None
    errors = 0
    for meta in lab.store.iter_metadata(max_names=lab.max_artifacts):
        kind, stamp = meta['artifact_type'], meta['created_at_utc']
        latest[kind] = max(latest.get(kind, stamp), stamp)
        if kind == 'reference_acquisition':
            last_observed = max(last_observed or meta['time_max'], meta['time_max'])
        errors += kind == 'collection_error' and utc(stamp) >= now_utc()-timedelta(days=7)
    return dict(root=str(field_lab_root()), usage=usage(lab), scheduler=scheduler('status'),
                last_success=latest.get('collection_success'), last_forecast=latest.get('reference_forecast'),
                last_acquisition=latest.get('reference_acquisition'), last_official_observation=last_observed,
                last_comparison=latest.get('reference_comparison_state'),
                comparison_time_unavailable=('reference_comparison' in latest and 'reference_comparison_state' not in latest),
                recent_errors=errors)


class BoundedLogHandler(logging.Handler):
    """Pinned root, no-follow files, 1 MiB each, three backups, bounded records."""
    def emit(self, record):
        if fcntl is None or os.name != 'posix':
            raise RuntimeError('field_lab_secure_lock_unavailable')
        data = (self.format(record)[:65535] + '\n').encode('utf-8')[:65536]
        with ReferenceLab().store._directory(root_only=True) as fd:
            lock = os.open('.collection-log.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
            with os.fdopen(lock, 'rb') as lock_stream:
                if not stat.S_ISREG(os.fstat(lock_stream.fileno()).st_mode):
                    raise ValueError('field_lab_log_lock_regular_file_required')
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
                for name in ('collection.log', 'collection.log.1', 'collection.log.2', 'collection.log.3'):
                    try:
                        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError('field_lab_log_regular_file_required')
                try:
                    size = os.stat('collection.log', dir_fd=fd, follow_symlinks=False).st_size
                except FileNotFoundError:
                    size = 0
                if size + len(data) > 1024*1024:
                    for source, destination in (('collection.log.2', 'collection.log.3'),
                                                ('collection.log.1', 'collection.log.2'),
                                                ('collection.log', 'collection.log.1')):
                        try:
                            os.rename(source, destination, src_dir_fd=fd, dst_dir_fd=fd)
                        except FileNotFoundError:
                            pass
                handle = os.open('collection.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 0o600, dir_fd=fd)
                with os.fdopen(handle, 'ab') as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError('field_lab_log_regular_file_required')
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(fd)


def scheduled_main():
    """Separate bounded logs; launchd receives no unbounded stdout/stderr files."""
    if fcntl is None or os.name != 'posix':
        raise RuntimeError('field_lab_secure_lock_unavailable')
    require_initialized(ReferenceLab())
    logger = logging.getLogger('field-lab')
    handler = BoundedLogHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        result = cycle(ReferenceLab(max_artifacts=CAPACITY))
        logger.info(json.dumps(result, allow_nan=False))
        return 0
    except Exception as error:
        logger.exception('collection failed: %s', error)
        record_error(error)
        return 2
    finally:
        handler.close()
        logger.removeHandler(handler)


def record_error(error):
    """At most one failure envelope per hour; detailed attempts stay in rotating log."""
    try:
        lab = ReferenceLab(max_artifacts=CAPACITY)
        with lab.store._directory(root_only=True):
            pass
        with lab.store.writer_lock(max_names=CAPACITY):
            check_capacity(lab)
            _record_error_locked(lab, error)
    except (ValueError, RuntimeError, OSError):
        pass


def _record_error_locked(lab, error):
    try:
        stamp = now_utc().replace(minute=0, second=0, microsecond=0).isoformat()
        key = 'error-'+digest(stamp)
        if lab.store.load(idempotency_key=key) is None:
            lab.save('collection_error', key, {'at_utc': stamp, 'error': str(error)}, stamp)
    except (ValueError, RuntimeError, OSError):
        # Original failure remains visible on stderr/log even when storage is invalid/full.
        pass

if __name__ == '__main__':
    raise SystemExit(scheduled_main())
