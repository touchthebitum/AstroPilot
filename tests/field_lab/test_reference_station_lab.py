from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astropilot.field_lab_store import FileFieldLabStore
from astropilot.reference_station_lab import (
    MeteoSwissReferenceClient, ReferenceForecastRun, ReferenceLab, ReferenceObservation,
    ReferenceStation, capture_forecast, compare_point, digest, parse_observations,
    report, select_stations, validate_tolerance, canonical_utc, ReferenceComparison,
)
from astropilot.reference_station_cli import main

_compare_point = compare_point
def compare_point(*args, **kwargs):
    kwargs.setdefault('durable_sealed_at_utc', canonical_utc(T-timedelta(minutes=58)))
    return _compare_point(*args, **kwargs)


FIXTURES = Path(__file__).parent / 'fixtures'
T = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
STATION = ReferenceStation('NEU', 'Neuchâtel', 47.000067, 6.953297, 485,
                           ('tre200s0', 'ure200s0', 'fu3010z0'), 'a' * 64)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELD_LAB_DATA_DIR', str(tmp_path / 'lab'))
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path / 'user'))
    return ReferenceLab()


def fake_snapshot():
    return SimpleNamespace(retrieved_at_utc=T-timedelta(hours=1), timezone='Europe/Zurich',
        payload={'hourly': {'time': [(T-timedelta(hours=2)).timestamp(), T.timestamp()],
            'temperature_2m': [1, 12], 'relative_humidity_2m': [2, 85], 'wind_speed_10m': [3, 4]}},
        trust_transport=lambda: {'provider': 'Open-Meteo', 'requested_latitude': STATION.latitude,
            'requested_longitude': STATION.longitude, 'grid_latitude': 47., 'grid_longitude': 7.,
            'elevation_m': 485})


def run():
    return capture_forecast(STATION, provider=lambda lat, lon: fake_snapshot(),
        clock=lambda: T-timedelta(minutes=59), build=('a' * 40, '1.0.0b7'))


def observations():
    return parse_observations((FIXTURES/'measurements.csv').read_text(), 'NEU',
                              T+timedelta(hours=1), 'https://data.geo.admin.ch/test')


def point(r):
    return json.loads(r.snapshot_json)['points'][0]


class MetadataSession:
    def get(self, url, **kwargs):
        name = url.split('_meta_')[1]
        return SimpleNamespace(status_code=200, content=(FIXTURES/name).read_bytes(), close=lambda: None)


def test_official_catalogue_and_variable_units():
    stations = MeteoSwissReferenceClient(MetadataSession()).stations()
    assert [s.station_id for s in stations] == ['CDF', 'NEU']
    assert stations[1].name == 'Neuchâtel'
    assert stations[1].altitude_m == 485
    assert stations[1].source == 'MeteoSwiss'
    assert len(select_stations(stations, ['NEU'])) == 1
    with pytest.raises(ValueError, match='unavailable'):
        select_stations(stations, ['JUN'])
    with pytest.raises(ValueError):
        select_stations(stations, ['NEU', 'NEU'])


def test_changed_metadata_units_fail_closed():
    class Session(MetadataSession):
        def get(self, url, **kwargs):
            response = super().get(url, **kwargs)
            if '_meta_parameters' in url:
                response.content = response.content.replace(b'km/h', b'mph')
            return response
    with pytest.raises(ValueError, match='contract_changed'):
        MeteoSwissReferenceClient(Session()).stations()


def test_observation_missing_qc_and_utc():
    obs = observations()
    assert len(obs) == 9  # Future row omitted.
    assert obs[0].value == 10 and obs[0].unit == '°C'
    assert obs[3].quality == 'missing' and obs[3].value is None
    assert obs[4].quality == 'invalid_value' and obs[4].value is None
    assert obs[6].quality == 'invalid_qc' and obs[6].value is None
    assert all(o.source == 'MeteoSwiss' for o in obs)
    with pytest.raises(ValueError):
        parse_observations((FIXTURES/'measurements.csv').read_text(), 'CDF', T, '')
    with pytest.raises(ValueError):
        parse_observations((FIXTURES/'measurements.csv').read_text(), 'NEU', T.replace(tzinfo=None), '')


def test_snapshot_captures_exact_coordinates_without_user_project():
    calls = []
    r = capture_forecast(STATION, provider=lambda lat, lon: calls.append((lat, lon)) or fake_snapshot(),
        clock=lambda: T-timedelta(minutes=59), build=('a'*40, '1.0.0b7'))
    assert calls == [(STATION.latitude, STATION.longitude)]
    assert r == run()
    assert len(json.loads(r.snapshot_json)['points']) == 1
    assert r.prospective is True
    with pytest.raises(ValueError, match='digest_mismatch'):
        replace(r, code_sha='b'*40)


def test_leakage_run_creation_rejected():
    r = run()
    fields = asdict(r)
    fields['created_at_utc'] = T.isoformat()
    fields['run_id'] = digest({k:v for k,v in fields.items() if k != 'run_id'})
    with pytest.raises(ValueError, match='leakage_detected'):
        ReferenceForecastRun(**fields)


def test_observation_before_retrieval_is_leakage_even_in_tolerance():
    r = run()
    obs = replace(observations()[0], observed_at_utc=(T-timedelta(hours=1)).isoformat())
    c = compare_point(r, point(r), obs.variable, [obs], 30)
    assert c.reason == 'leakage_detected' and c.signed_error is None


def test_matching_errors_and_wind_semantics():
    r = run()
    c = compare_point(r, point(r), 'temperature_2m', observations(), 10)
    assert c.status == 'comparable' and c.signed_error == 2 and c.absolute_error == 2
    assert c.temporal_offset_minutes == 0
    assert compare_point(r, point(r), 'wind_speed_10m', observations(), 10).reason == 'aggregation_semantics_unverified'
    shifted = replace(observations()[0], observed_at_utc=(T+timedelta(minutes=5)).isoformat())
    c = compare_point(r, point(r), shifted.variable, [shifted], 10)
    assert c.temporal_offset_minutes == -5
    assert compare_point(r, point(r), shifted.variable, [shifted], 1).reason == 'outside_time_tolerance'
    other = replace(shifted, observed_at_utc=(T-timedelta(minutes=5)).isoformat())
    assert compare_point(r, point(r), shifted.variable, [shifted, other], 10).reason == 'ambiguous_nearest_observation'
    assert compare_point(r, point(r), shifted.variable, [], 10).reason == 'missing_observation'


@pytest.mark.parametrize('tolerance', [-1, 31, float('nan'), True])
def test_invalid_tolerance(tolerance):
    with pytest.raises(ValueError):
        validate_tolerance(tolerance)


def test_store_sealing_idempotence_and_user_unchanged(lab, tmp_path):
    user = tmp_path/'user'
    user.mkdir()
    (user/'user_profile.json').write_text('{"sentinel": true}')
    before = {str(p):p.read_bytes() for p in user.rglob('*') if p.is_file()}
    r = run()
    assert lab.save_run(r, clock=lambda: T-timedelta(minutes=58))
    assert not lab.save_run(r, clock=lambda: T-timedelta(minutes=57))
    assert not lab.save_run(r, clock=lambda: T+timedelta(days=1))
    for obs in observations():
        assert lab.save_observation(obs)
        assert not lab.save_observation(obs)
        assert lab.save_observation(replace(obs, retrieved_at_utc=(T+timedelta(hours=2)).isoformat()))
    clock = lambda: T+timedelta(hours=1)
    first = lab.comparisons(clock=clock, persist=True)
    count = len(tuple(lab.store.iter_artifacts()))
    assert first == lab.comparisons(clock=clock, persist=True)
    assert len(tuple(lab.store.iter_artifacts())) == count
    rows = report(first, lab.facts()[0])
    temp = next(row for row in rows if row['station']=='NEU' and row['variable']=='temperature_2m')
    assert temp['n_comparable']==1 and temp['mean_bias']==2 and temp['mae']==2
    assert temp['p90_abs_error']==2 and temp['altitude_m']==485
    assert all(a.calibration_eligible is False and a.provenance=='field_lab_reference_station'
               for a in lab.store.iter_artifacts())
    assert {str(p):p.read_bytes() for p in user.rglob('*') if p.is_file()} == before


def test_unsealed_forecast_and_deadline_miss_excluded(lab):
    r = run()
    lab.save('reference_forecast', r.run_id, asdict(r), r.created_at_utc, r.station_id)
    assert lab.facts()[0] == ()
    with pytest.raises(ValueError, match='leakage_detected'):
        lab.save_run(r, clock=lambda: T)
    times = iter([T-timedelta(seconds=1), T])
    with pytest.raises(ValueError, match='deadline_missed'):
        lab.save_run(r, clock=lambda: next(times))
    assert lab.facts()[0] == ()


def test_collection_only_due_and_no_provider_reconstruction(lab):
    r = run()
    lab.save_run(r, clock=lambda: T-timedelta(minutes=58))
    calls = []
    client = SimpleNamespace(observations=lambda station, family: calls.append((station, family)) or observations())
    assert lab.collect(client, clock=lambda: T) == 0 and calls == []
    assert lab.collect(client, clock=lambda: T+timedelta(hours=1)) == 6
    assert calls == [('NEU','now')]
    assert lab.collect(client, clock=lambda: T+timedelta(hours=1)) == 0


def test_missing_can_become_comparable_without_double_count(lab):
    r = run()
    lab.save_run(r, clock=lambda: T-timedelta(minutes=58))
    clock = lambda: T+timedelta(hours=1)
    assert all(c.status=='non_comparable' for c in lab.comparisons(clock=clock,persist=True))
    lab.save_observation(observations()[0])
    comparisons = lab.comparisons(clock=clock,persist=True)
    assert len(comparisons)==3
    assert sum(c.status=='comparable' for c in comparisons)==1


def test_cli_cycle_dry_run_is_offline_and_creates_nothing(lab, tmp_path, capsys, monkeypatch):
    import astropilot.reference_station_cli as cli
    monkeypatch.setattr(cli, 'MeteoSwissReferenceClient', lambda: pytest.fail('network client constructed'))
    assert main(['cycle','--dry-run'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['network_calls']==0 and result['writes']==0
    assert not (tmp_path/'lab').exists()


def test_reader_fail_closed_symlink_corruption_and_capability(lab, tmp_path, monkeypatch):
    r=run()
    lab.save_run(r,clock=lambda:T-timedelta(minutes=58))
    path=next((tmp_path/'lab'/'artifacts').glob('*.json'))
    contents=path.read_text();path.unlink();path.symlink_to(tmp_path/'other')
    with pytest.raises(OSError):
        tuple(lab.store.iter_artifacts())
    path.unlink();path.write_text(contents.replace('"digest":', '"unknown_digest":'))
    with pytest.raises(ValueError):
        tuple(lab.store.iter_artifacts())
    import astropilot.field_lab_store as storage
    monkeypatch.setattr(storage.os,'supports_dir_fd',set())
    with pytest.raises(RuntimeError,match='secure_storage_unavailable'):
        FileFieldLabStore()


def test_historical_separate_default_exclusion(lab):
    fields=asdict(run());fields['prospective']=False
    fields['run_id']=digest({k:v for k,v in fields.items() if k!='run_id'})
    r=ReferenceForecastRun(**fields)
    lab.save_run(r,clock=lambda:T+timedelta(hours=1))
    assert lab.comparisons(clock=lambda:T+timedelta(hours=1))==()
    assert all(c.cohort=='historical_backfill' for c in lab.comparisons(clock=lambda:T+timedelta(hours=1),historical=True))


def test_catalogue_snapshot_rerun_with_tuple_parameters(lab):
    payload = {'stations':[asdict(STATION)], 'active_station_ids':['NEU']}
    assert lab.save('reference_catalogue', digest(payload), payload, T.isoformat())
    assert not lab.save('reference_catalogue', digest(payload), payload, (T+timedelta(hours=1)).isoformat())
    with pytest.raises(ValueError,match='immutable_conflict'):
        lab.save('reference_catalogue', digest(payload), {'stations':[]}, T.isoformat())


def test_revision_missing_invalid_and_future_pair_refusal():
    r=run()
    base=observations()[0]
    missing=replace(base,value=None,quality='missing')
    assert compare_point(r,point(r),base.variable,[missing],10).reason=='missing'
    invalid=replace(base,value=None,quality='invalid_qc')
    assert compare_point(r,point(r),base.variable,[invalid],10).reason=='invalid_qc'
    revised=replace(base,value=11,retrieved_at_utc=(T+timedelta(hours=2)).isoformat())
    c=compare_point(r,point(r),base.variable,[base,revised],10)
    assert c.observed_value==11 and c.observation_digest==revised.measurement_digest
    assert datetime.fromisoformat(r.forecast_retrieved_at_utc)<datetime.fromisoformat(c.observation_at_utc)
    with pytest.raises(ValueError,match='future_reference_observation'):
        replace(base,retrieved_at_utc=(T-timedelta(minutes=1)).isoformat())


def test_delayed_seal_publication_and_no_retroactive_recovery(lab, monkeypatch):
    r = run()
    current = T-timedelta(seconds=1)
    original = lab.store.save
    def delayed(artifact):
        nonlocal current
        result = original(artifact)
        if artifact.artifact_type == 'reference_seal':
            current = T+timedelta(seconds=1)
        return result
    monkeypatch.setattr(lab.store, 'save', delayed)
    with pytest.raises(ValueError, match='deadline_missed'):
        lab.save_run(r, clock=lambda: current)
    assert lab.facts()[0] == ()
    with pytest.raises(ValueError):
        lab.save_run(r, clock=lambda: current)
    assert lab.facts()[0] == ()


def test_durable_snapshot_delay(lab, monkeypatch):
    current = T-timedelta(seconds=1)
    original = lab.store.save
    def delayed(artifact):
        nonlocal current
        result = original(artifact)
        if artifact.artifact_type == 'reference_forecast':
            current = T+timedelta(seconds=1)
        return result
    monkeypatch.setattr(lab.store, 'save', delayed)
    with pytest.raises(ValueError, match='deadline_missed'):
        lab.save_run(run(), clock=lambda: current)
    assert lab.facts()[0] == ()


def test_seal_required_before_observation():
    r = run()
    obs = replace(observations()[0], observed_at_utc=canonical_utc(T-timedelta(minutes=10)))
    assert _compare_point(r, point(r), obs.variable, [obs], 10).reason == 'missing_durable_seal'
    assert _compare_point(r, point(r), obs.variable, [obs], 10,
        durable_sealed_at_utc=canonical_utc(T-timedelta(minutes=5))).reason == 'leakage_detected'
    assert _compare_point(r, point(r), obs.variable, [obs], 10,
        durable_sealed_at_utc=canonical_utc(T-timedelta(minutes=11))).status == 'comparable'


def test_seal_mismatch(lab):
    r = run()
    lab.save('reference_forecast', r.run_id, asdict(r), r.created_at_utc, r.station_id)
    lab.save('reference_seal', 'seal-'+r.run_id,
        {'run_id':r.run_id, 'snapshot_digest':'f'*64}, canonical_utc(T-timedelta(minutes=30)), r.station_id)
    lab.save('reference_seal_completion', 'durable-'+r.run_id, {}, canonical_utc(T-timedelta(minutes=29)), r.station_id)
    with pytest.raises(ValueError, match='seal_identity_mismatch'):
        lab.facts()


def test_revision_a_b_a_and_event_idempotence(lab):
    r = run()
    lab.save_run(r, clock=lambda:T-timedelta(minutes=58))
    a = observations()[0]
    b = replace(a, value=11, retrieved_at_utc=canonical_utc(T+timedelta(hours=2)))
    a3 = replace(a, retrieved_at_utc=canonical_utc(T+timedelta(hours=3)))
    for event in (a3, a, b):
        assert lab.save_observation(event)
        assert not lab.save_observation(event)
        assert not lab.save_observation(replace(event, asset_href="https://data.geo.admin.ch/alias"))
    assert len(lab.facts()[1]) == 3
    c = next(c for c in lab.comparisons(clock=lambda:T+timedelta(hours=4)) if c.variable == a.variable)
    assert c.observed_value == 10
    with pytest.raises(ValueError, match='immutable_conflict'):
        lab.save('reference_acquisition', a.acquisition_id, asdict(b), a.retrieved_at_utc, a.station_id)


def test_timestamp_equivalence_microseconds_and_offsets():
    a = observations()[0]
    b = replace(a, observed_at_utc=a.observed_at_utc.replace('Z', '+00:00'))
    assert a == b and a.measurement_digest == b.measurement_digest and a.acquisition_id == b.acquisition_id
    assert canonical_utc('2026-10-05T12:00:00.123456+00:00') == '2026-10-05T12:00:00.123456Z'
    with pytest.raises(ValueError, match='utc_required'):
        canonical_utc('2026-10-25T02:30:00+02:00')
    r = run()
    fields = asdict(r)
    fields['created_at_utc'] = fields['created_at_utc'].replace('Z', '+00:00')
    assert ReferenceForecastRun(**fields) == r


@pytest.mark.parametrize('change', [
    {'schema_version':999}, {'forecast_point_at_utc':'bad'}, {'forecast_point_at_utc':None},
    {'temporal_offset_minutes':5}, {'observed_value':1000}, {'source':'forged'},
    {'cohort':'fake'}, {'signed_error':float('nan')}, {'absolute_error':float('inf')},
    {'signed_error':99}, {'status':'non_comparable'}, {'observed_value':float('nan')},
])
def test_strict_comparison_forgery(change):
    r = run()
    c = compare_point(r, point(r), 'temperature_2m', observations(), 10)
    with pytest.raises(ValueError):
        replace(c, **change)
    object.__setattr__(c, next(iter(change)), next(iter(change.values())))
    with pytest.raises(ValueError):
        report([c], [r])
    with pytest.raises(ValueError):
        report([asdict(c)], [r])


def test_artifact_limit(lab):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    lab.max_artifacts = 1
    with pytest.raises(ValueError, match='(artifact|name)_limit'):
        lab.facts()


def test_hours_zero_rejected_before_store(monkeypatch, capsys):
    import astropilot.reference_station_cli as cli
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:pytest.fail('store constructed'))
    for options in ([], ['--dry-run']):
        assert main(['forecast-run', '--hours', '0', *options]) == 2
        assert 'reference_hours' in capsys.readouterr().err


def test_sync_identical_noop(lab, monkeypatch):
    import astropilot.reference_station_cli as cli
    from astropilot.field_lab_collection import initialize
    initialize()
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:lab)
    monkeypatch.setattr(cli, 'MeteoSwissReferenceClient', lambda:SimpleNamespace(stations=lambda:(STATION,)))
    monkeypatch.setattr(cli, 'now_utc', lambda:T)
    assert main(['stations', 'sync', '--stations', 'NEU']) == 0
    assert main(['stations', 'sync', '--stations', 'NEU']) == 0
    assert len(tuple(lab.store.iter_artifacts())) == 2


def test_unsorted_snapshot_points_rejected():
    r = run()
    fields = asdict(r)
    snapshot = json.loads(r.snapshot_json)
    later = dict(snapshot['points'][0], at=canonical_utc(T+timedelta(hours=1)))
    snapshot['points'] = [later, snapshot['points'][0]]
    fields['snapshot_json'] = json.dumps(snapshot)
    fields['run_id'] = digest({k:v for k,v in fields.items() if k != 'run_id'})
    with pytest.raises(ValueError, match='forecast_times'):
        ReferenceForecastRun(**fields)


@pytest.mark.parametrize('late', [False, True])
def test_seal_fsync_failure_retry_current_completion(lab, monkeypatch, late):
    import os
    import stat
    import astropilot.field_lab_store as storage
    r = run()
    original = os.fsync
    seal_name = lab.store._name('seal-' + r.run_id)
    def fail_visible_seal_dir(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) and seal_name in os.listdir(fd):
            raise OSError('seal directory fsync failed')
        original(fd)
    monkeypatch.setattr(storage.os, 'fsync', fail_visible_seal_dir)
    with pytest.raises(OSError, match='seal directory'):
        lab.save_run(r, clock=lambda:T-timedelta(minutes=58))
    assert lab.store.load(idempotency_key='seal-' + r.run_id) is not None
    assert lab.store.load(idempotency_key='durable-' + r.run_id) is None
    monkeypatch.setattr(storage.os, 'fsync', original)
    current = T-timedelta(minutes=57)
    confirm = lab.store.confirm_durable
    seen = []
    def reconfirm(artifact):
        nonlocal current
        confirm(artifact)
        seen.append(artifact.artifact_type)
        if artifact.artifact_type == 'reference_seal':
            current = T+timedelta(seconds=1) if late else T-timedelta(minutes=56)
    monkeypatch.setattr(lab.store, 'confirm_durable', reconfirm)
    if late:
        with pytest.raises(ValueError, match='deadline_missed'):
            lab.save_run(r, clock=lambda:current)
    else:
        lab.save_run(r, clock=lambda:current)
    assert seen == ['reference_forecast', 'reference_seal']
    assert lab.durable_seal(r) == canonical_utc(current)
    assert len(lab.facts()[0]) == (0 if late else 1)
    if late:
        with pytest.raises(ValueError):
            lab.save_run(r, clock=lambda:T+timedelta(minutes=1))
        assert lab.durable_seal(r) == canonical_utc(current)


@pytest.mark.parametrize('stage', ['before_file', 'before_dir', 'after_dir', 'before_proof'])
def test_reconfirmation_crash_no_proof(lab, monkeypatch, stage):
    import os
    import stat
    r = run()
    lab.save('reference_forecast', r.run_id, asdict(r), r.created_at_utc, r.station_id)
    lab.save('reference_seal', 'seal-' + r.run_id,
             {'run_id':r.run_id, 'snapshot_digest':r.snapshot_digest},
             T-timedelta(minutes=58), r.station_id)
    original = os.fsync
    confirming = False
    confirm = lab.store.confirm_durable
    def fault(fd):
        if confirming and ((stage == 'before_file' and stat.S_ISREG(os.fstat(fd).st_mode))
                           or (stage == 'before_dir' and stat.S_ISDIR(os.fstat(fd).st_mode))):
            raise OSError('crash')
        original(fd)
    def reconfirm(artifact):
        nonlocal confirming
        confirming = True
        try:
            confirm(artifact)
            if stage == 'after_dir':
                raise OSError('crash')
        finally:
            confirming = False
    monkeypatch.setattr(os, 'fsync', fault)
    monkeypatch.setattr(lab.store, 'confirm_durable', reconfirm)
    save = lab.save
    def publish(kind, *args, **kwargs):
        if kind == 'reference_seal_completion' and stage == 'before_proof':
            raise OSError('crash')
        return save(kind, *args, **kwargs)
    monkeypatch.setattr(lab, 'save', publish)
    with pytest.raises(OSError, match='crash'):
        lab.save_run(r, clock=lambda:T-timedelta(minutes=57))
    assert lab.store.load(idempotency_key='durable-' + r.run_id) is None
    assert lab.facts()[0] == ()


@pytest.mark.parametrize('order', [(0, 1, 2), (2, 0, 1)])
def test_catalog_activation_return_and_ingestion_order(lab, order):
    from astropilot.reference_station_cli import saved_catalogue
    a = {'stations':[asdict(STATION)], 'active_station_ids':['NEU']}
    b = {'stations':[asdict(replace(STATION, altitude_m=500))], 'active_station_ids':['NEU']}
    events = [(a, T), (b, T+timedelta(hours=1)), (a, T+timedelta(hours=2))]
    for i in order:
        assert lab.save_catalogue(*events[i])
    assert not lab.save_catalogue(*events[2])
    assert saved_catalogue(lab)[0][0].altitude_m == 485
    artifacts = tuple(lab.store.iter_artifacts())
    assert sum(a.artifact_type == 'reference_catalogue' for a in artifacts) == 2
    assert sum(a.artifact_type == 'catalog_activation_event' for a in artifacts) == 3
    assert lab.facts() == ((), ())


def test_catalog_same_content_new_time_tie_and_conflict(lab):
    from astropilot.reference_station_cli import saved_catalogue
    a = {'stations':[asdict(STATION)], 'active_station_ids':['NEU']}
    b = {'stations':[asdict(replace(STATION, altitude_m=500))], 'active_station_ids':['NEU']}
    assert lab.save_catalogue(a, T, event_id='event-one')
    with pytest.raises(ValueError, match='immutable_conflict'):
        lab.save_catalogue(b, T, event_id='event-one')
    lab.save_catalogue(a, T+timedelta(hours=1))
    assert len(tuple(lab.store.iter_artifacts())) == 3
    lab.save_catalogue(b, T+timedelta(hours=1))
    with pytest.raises(ValueError, match='reference_catalogue_activation_ambiguous'):
        saved_catalogue(lab)


@pytest.mark.parametrize('limit, succeeds', [(2, False), (3, True), (4, True)])
def test_name_limit_before_payload_reads(lab, monkeypatch, limit, succeeds):
    for i in range(3):
        lab.save('test', str(i), {'i':i}, T)
    if succeeds:
        assert len(tuple(lab.store.iter_artifacts(max_names=limit))) == 3
    else:
        read = lab.store._read
        def no_payload(fd, name):
            if name.endswith('.json'):
                pytest.fail('payload read before enumeration limit')
            return read(fd, name)
        monkeypatch.setattr(lab.store, '_read', no_payload)
        with pytest.raises(ValueError, match='field_lab_name_limit_exceeded'):
            tuple(lab.store.iter_artifacts(max_names=limit))


def test_unverified_missing_rejected_at_ingestion(lab):
    obs = observations()[0]
    with pytest.raises(ValueError, match='unverified_missing'):
        replace(obs, value=None)
    missing = replace(obs, value=None, quality='missing')
    lab.save_observation(missing)
    assert lab.facts()[1] == (missing,)
    comparison = compare_point(run(), point(run()), 'temperature_2m', [missing], 10)
    assert comparison.status == 'non_comparable'
    assert comparison.observed_value is None


@pytest.mark.parametrize('late', [False, True])
def test_candidate_visible_directory_failure_replay(lab, monkeypatch, late):
    import os
    import stat
    r = run()
    original = os.fsync
    def fault(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            for name in os.listdir(fd):
                if name.endswith('.json'):
                    value = json.loads(lab.store._read(fd, name))
                    if value.get('artifact_type') == 'reference_seal_completion':
                        raise OSError('candidate directory failure')
        original(fd)
    monkeypatch.setattr(os, 'fsync', fault)
    with pytest.raises(OSError, match='candidate directory failure'):
        lab.save_run(r, clock=lambda:T-timedelta(minutes=58))
    assert lab.facts()[0] == ()
    assert lab.store.load(idempotency_key='commit-'+r.run_id) is None
    monkeypatch.setattr(os, 'fsync', original)
    current = T+timedelta(seconds=1) if late else T-timedelta(seconds=1)
    if late:
        with pytest.raises(ValueError, match='deadline_missed'):
            lab.save_run(r, clock=lambda:current)
    else:
        lab.save_run(r, clock=lambda:current)
        assert not lab.save_run(r, clock=lambda:T+timedelta(days=1))
    assert lab.durable_seal(r) == canonical_utc(current)
    assert len(lab.facts()[0]) == (0 if late else 1)
    assert sum(a.artifact_type == 'reference_seal_completion'
               for a in lab.store.iter_artifacts()) == 2


def test_crash_between_candidate_and_commit(lab, monkeypatch):
    save = lab.store.save
    def fault(artifact):
        if artifact.artifact_type == 'reference_seal_commit':
            raise OSError('crash before commit')
        return save(artifact)
    monkeypatch.setattr(lab.store, 'save', fault)
    with pytest.raises(OSError, match='crash before commit'):
        lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    assert lab.facts()[0] == ()


@pytest.mark.parametrize('field', ['run_id', 'snapshot_digest', 'seal_digest', 'candidate_digest', 'candidate_key'])
def test_commit_binding_mismatch(lab, monkeypatch, field):
    from astropilot.field_lab_store import FieldLabArtifact
    r = run()
    lab.save_run(r, clock=lambda:T-timedelta(minutes=58))
    load = lab.store.load
    def corrupt(*, idempotency_key):
        artifact = load(idempotency_key=idempotency_key)
        if idempotency_key == 'commit-'+r.run_id:
            payload = json.loads(artifact.payload_json)
            payload[field] = 'f'*64
            return FieldLabArtifact.create(artifact_type=artifact.artifact_type,
                source_id=artifact.source_id, idempotency_key=idempotency_key,
                payload=payload, created_at_utc=artifact.created_at_utc)
        return artifact
    monkeypatch.setattr(lab.store, 'load', corrupt)
    with pytest.raises(ValueError, match='seal_identity_mismatch'):
        lab.facts()
    with pytest.raises(ValueError, match='seal_identity_mismatch'):
        lab.save_run(r)


@pytest.mark.parametrize('reverse', [False, True])
def test_catalog_equal_timestamp_divergence_cli(lab, monkeypatch, capsys, reverse):
    from astropilot.reference_station_cli import saved_catalogue
    a = {'stations':[asdict(STATION)], 'active_station_ids':['NEU']}
    b = {'stations':[asdict(replace(STATION, altitude_m=500))], 'active_station_ids':['NEU']}
    for value in ([b, a] if reverse else [a, b]):
        lab.save_catalogue(value, T)
    with pytest.raises(ValueError, match='activation_ambiguous'):
        saved_catalogue(lab)
    assert main(['stations', 'list']) == 2
    assert 'reference_catalogue_activation_ambiguous' in capsys.readouterr().err


def test_catalog_equal_timestamp_same_content(lab):
    from astropilot.reference_station_cli import saved_catalogue
    a = {'stations':[asdict(STATION)], 'active_station_ids':['NEU']}
    lab.save_catalogue(a, T, event_id='one')
    lab.save_catalogue(a, T, event_id='two')
    assert saved_catalogue(lab)[0] == (STATION,)


def test_orphan_candidate_conflict(lab, monkeypatch):
    r = run()
    lab.save('reference_forecast', r.run_id, asdict(r), r.created_at_utc, r.station_id)
    lab.save('reference_seal', 'seal-'+r.run_id,
        {'run_id':r.run_id, 'snapshot_digest':r.snapshot_digest}, T-timedelta(minutes=58), r.station_id)
    lab.save('reference_seal_completion', 'candidate-'+r.run_id+'-orphan',
        {'run_id':r.run_id, 'snapshot_digest':'f'*64, 'seal_digest':'f'*64}, T-timedelta(minutes=58), r.station_id)
    with pytest.raises(ValueError, match='seal_identity_mismatch'):
        lab.save_run(r, clock=lambda:T-timedelta(minutes=57))


def test_commit_directory_failure_removes_visible_commit(lab, monkeypatch):
    import os
    import stat
    r = run()
    original = os.fsync
    name = lab.store._name('commit-'+r.run_id)
    def fault(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) and name in os.listdir(fd):
            raise OSError('commit directory failure')
        original(fd)
    monkeypatch.setattr(os, 'fsync', fault)
    with pytest.raises(OSError, match='commit directory failure'):
        lab.save_run(r, clock=lambda:T-timedelta(minutes=58))
    assert lab.facts()[0] == ()


@pytest.mark.parametrize('stage', ['candidate_file', 'candidate_cleanup', 'candidate_delayed'])
def test_candidate_publication_boundary(lab, monkeypatch, stage):
    import os
    import stat
    r = run()
    original = os.fsync
    current = T-timedelta(seconds=1)
    publishing = False
    calls = 0
    def fault(fd):
        nonlocal calls, current
        if publishing:
            calls += 1
            if stage == 'candidate_file' and stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError('candidate file failure')
            if stage == 'candidate_cleanup' and calls == 3:
                raise OSError('candidate cleanup failure')
        original(fd)
    save = lab.store.save
    def publish(artifact):
        nonlocal publishing, current
        publishing = artifact.artifact_type == 'reference_seal_completion'
        try:
            result = save(artifact)
            if publishing and stage == 'candidate_delayed':
                current = T+timedelta(seconds=1)
            return result
        finally:
            publishing = False
    monkeypatch.setattr(os, 'fsync', fault)
    monkeypatch.setattr(lab.store, 'save', publish)
    if stage == 'candidate_delayed':
        with pytest.raises(ValueError, match='deadline_missed'):
            lab.save_run(r, clock=lambda:current)
        assert lab.durable_seal(r) == canonical_utc(current)
    else:
        with pytest.raises(OSError, match='candidate'):
            lab.save_run(r, clock=lambda:current)
        assert lab.store.load(idempotency_key='commit-'+r.run_id) is None
    assert lab.facts()[0] == ()


@pytest.mark.parametrize('outcome', ['delayed', 'failure'])
def test_visible_commit_attests_prior_forecast_barrier(lab, monkeypatch, outcome):
    import os
    import stat
    r = run()
    current = T-timedelta(seconds=1)
    barrier_time = current
    original = os.fsync
    name = lab.store._name('commit-'+r.run_id)
    seen = []
    def boundary(fd):
        nonlocal current
        if stat.S_ISDIR(os.fstat(fd).st_mode) and name in os.listdir(fd):
            # A fresh reader observes the process-interruption window.
            reader = ReferenceLab(FileFieldLabStore())
            assert reader.facts()[0] == (r,)
            assert reader.durable_seal(r) == canonical_utc(barrier_time)
            current = T+timedelta(seconds=1)
            assert reader.save_run(r, clock=lambda:current) is False
            seen.append(True)
            if outcome == 'failure':
                raise OSError('attestation persistence failed')
        original(fd)
    monkeypatch.setattr(os, 'fsync', boundary)
    if outcome == 'failure':
        with pytest.raises(OSError, match='attestation persistence failed'):
            lab.save_run(r, clock=lambda:current)
        assert lab.facts()[0] == ()
    else:
        assert lab.save_run(r, clock=lambda:current)
        assert lab.facts()[0] == (r,)
        assert lab.durable_seal(r) == canonical_utc(barrier_time)
    assert seen


def test_disappeared_attestation_is_false_negative(lab):
    import os
    r = run()
    lab.save_run(r, clock=lambda:T-timedelta(seconds=1))
    with lab.store._directory() as fd:
        os.unlink(lab.store._name('commit-'+r.run_id), dir_fd=fd)
        os.fsync(fd)
    assert lab.facts()[0] == ()
    with pytest.raises(ValueError, match='deadline_missed'):
        lab.save_run(r, clock=lambda:T+timedelta(seconds=1))
    assert lab.facts()[0] == ()


def test_process_exit_with_visible_commit_preserves_prior_barrier(lab):
    import subprocess
    import sys
    r = run()
    stamp = canonical_utc(T-timedelta(seconds=1))
    script = '''
import json, os, stat, sys
from astropilot.reference_station_lab import ReferenceLab, ReferenceForecastRun, utc
lab = ReferenceLab()
run = ReferenceForecastRun(**json.loads(sys.argv[1]))
name = lab.store._name('commit-'+run.run_id)
original = os.fsync
def interrupted(fd):
    if stat.S_ISDIR(os.fstat(fd).st_mode) and name in os.listdir(fd):
        os._exit(73)
    original(fd)
os.fsync = interrupted
lab.save_run(run, clock=lambda:utc(sys.argv[2]))
'''
    result = subprocess.run([sys.executable, '-c', script, json.dumps(asdict(r)), stamp])
    assert result.returncode == 73
    reader = ReferenceLab(FileFieldLabStore())
    assert reader.facts()[0] == (r,)
    assert reader.durable_seal(r) == stamp
    assert reader.save_run(r, clock=lambda:T+timedelta(seconds=1)) is False


def collection_catalogue(lab):
    lab.save_catalogue(dict(schema_version=1, source='MeteoSwiss', collection='ch.meteoschweiz.ogd-smn',
        stations=[asdict(STATION)], active_station_ids=['NEU'], selection_version='smn-prospective-v1'),
        T.isoformat())


def test_bounded_cycle_noop_restart_and_user_unchanged(lab, tmp_path):
    from astropilot.field_lab_collection import cycle, initialize
    initialize()
    collection_catalogue(lab)
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    calls = []
    client = SimpleNamespace(observations=lambda *args: calls.append(args) or observations(),
                             stations=lambda:pytest.fail('catalogue not due'))
    first = cycle(lab, clock=lambda:T+timedelta(hours=1), client=client,
                  capture=lambda *a, **kw:pytest.fail('forecast not due'))
    before = sorted((p.name, p.read_bytes()) for p in (tmp_path/'lab'/'artifacts').iterdir())
    second = cycle(ReferenceLab(), clock=lambda:T+timedelta(hours=1, minutes=1), client=client)
    assert second['no_op'] and second['writes'] == second['network_calls'] == 0
    assert len(calls) == 1 and first['acquisitions_created'] > 0
    assert before == sorted((p.name, p.read_bytes()) for p in (tmp_path/'lab'/'artifacts').iterdir())
    assert not (tmp_path/'user').exists()


def test_acquisition_coalescing_revision_a_b_a_and_horizon(lab):
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    a = next(o for o in observations() if o.variable == 'temperature_2m')
    collect = lambda observation:lab.collect(SimpleNamespace(observations=lambda *args:[observation]),
        clock=lambda:T+timedelta(hours=2), revision_days=7, coalesce=True)
    assert collect(a) == 1
    assert collect(replace(a, retrieved_at_utc=canonical_utc(T+timedelta(hours=2)))) == 0
    b = replace(a, value=a.value+1, retrieved_at_utc=canonical_utc(T+timedelta(hours=3)))
    assert collect(b) == 1
    assert collect(replace(a, retrieved_at_utc=canonical_utc(T+timedelta(hours=4)))) == 1
    assert len(lab.facts()[1]) == 3
    assert lab.collect(SimpleNamespace(observations=lambda *a:pytest.fail('outside horizon')),
                       clock=lambda:T+timedelta(days=8), revision_days=7, coalesce=True) == 0


def test_collection_capacity_warning_stop_preserves_facts(lab):
    from astropilot.field_lab_collection import usage, check_capacity
    collection_catalogue(lab)
    lab.max_artifacts = 3
    assert usage(lab)['count'] == 2
    lab.max_artifacts = 2
    assert usage(lab)['warning'] and usage(lab)['blocked']
    before = [a.document() for a in lab.store.iter_artifacts()]
    with pytest.raises(ValueError, match='capacity_stop'):
        check_capacity(lab)
    assert before == [a.document() for a in lab.store.iter_artifacts()]


@pytest.mark.parametrize('period,days', [('24h',1), ('7d',7), ('30d',30), ('all',100)])
def test_longitudinal_period_prospective_only(lab, period, days):
    from astropilot.field_lab_collection import periodic_report
    lab.save_run(run(), clock=lambda:T-timedelta(minutes=58))
    for observation in observations():
        lab.save_observation(observation)
    rows = periodic_report(lab, period, clock=lambda:T+timedelta(days=days-0.5))
    assert rows and all(r['cohort'] == 'prospective' for r in rows)
    if period != 'all':
        assert periodic_report(lab, period, clock=lambda:T+timedelta(days=days+1)) == []


def test_scheduler_offline_plan_commands_and_uninstall(lab, monkeypatch):
    import astropilot.field_lab_collection as collection
    import plistlib
    from astropilot.reference_station_cli import parser
    calls = []
    monkeypatch.setattr(collection, 'launch_agents_path', lambda:collection.field_lab_root()/'launch-agents'/('test.plist'))
    def runner(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=1 if argv[1] == 'print' else 0)
    collection.initialize()
    assert collection.scheduler('install', runner=runner)['enabled'] is False
    assert calls == []
    value = plistlib.loads(collection.scheduler_path().read_bytes())
    assert value['StartInterval'] == 3600 and value['RunAtLoad'] is False
    assert 'StandardOutPath' not in value and 'StandardErrorPath' not in value
    assert value['EnvironmentVariables']['FIELD_LAB_DATA_DIR'] == str(collection.field_lab_root())
    monkeypatch.setattr(collection.sys, 'platform', 'darwin')
    collection.scheduler('enable', runner=runner)
    assert any(c[1] == 'bootstrap' for c in calls)
    collection.scheduler('disable', runner=runner)
    collection.scheduler('uninstall', runner=runner)
    assert not collection.scheduler_path().exists()
    for operation in ('install','status','enable','disable','uninstall'):
        assert parser().parse_args(['scheduler',operation]).operation == operation


def test_bounded_logs_and_symlink_refusal(lab, tmp_path):
    from astropilot.field_lab_collection import initialize, BoundedLogHandler
    import logging
    initialize()
    handler = BoundedLogHandler()
    for i in range(85):
        handler.emit(logging.LogRecord('test',20,'test',1,'x'*65536,(),None))
    logs = list((tmp_path/'lab').glob('collection.log*'))
    assert len(logs) == 4 and all(p.stat().st_size <= 1024*1024 for p in logs)
    (tmp_path/'lab'/'collection.log').unlink()
    (tmp_path/'lab'/'collection.log').symlink_to(tmp_path/'user')
    with pytest.raises(ValueError, match='regular_file'):
        handler.emit(logging.LogRecord('test',20,'test',1,'hello',(),None))
    assert not (tmp_path/'user').exists()


def test_collection_init_overlap_before_creation(tmp_path, monkeypatch):
    from astropilot.field_lab_collection import initialize
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path/'user'))
    monkeypatch.setenv('FIELD_LAB_DATA_DIR', str(tmp_path/'user'/'lab'))
    with pytest.raises(ValueError, match='overlap'):
        initialize()
    assert not (tmp_path/'user').exists()


def test_asset_audit_content_coalescence_and_reversion(lab):
    from astropilot.field_lab_collection import save_asset_audit
    payload = dict(station='NEU', family='now', asset_href='https://data.geo.admin.ch/now.csv',
                   sha256='a'*64, official_checksum='1220'+'a'*64, retrieved_at_utc=canonical_utc(T))
    assert save_asset_audit(lab,payload)
    assert not save_asset_audit(lab,dict(payload,retrieved_at_utc=canonical_utc(T+timedelta(hours=1))))
    assert save_asset_audit(lab,dict(payload,sha256='b'*64,official_checksum='1220'+'b'*64,
                                   retrieved_at_utc=canonical_utc(T+timedelta(hours=2))))
    assert save_asset_audit(lab,dict(payload,retrieved_at_utc=canonical_utc(T+timedelta(hours=3))))
    assert len(list(lab.store.iter_artifacts())) == 3


def test_write_budget_stops_partial_cycle_safely(lab):
    lab.write_budget = 1
    lab.save('collection_success','one',{'n':1},T.isoformat())
    assert not lab.save('collection_success','one',{'n':1},T.isoformat())
    with pytest.raises(ValueError,match='capacity_stop'):
        lab.save('collection_success','two',{'n':2},T.isoformat())
    assert len(list(lab.store.iter_artifacts())) == 1


def test_scheduler_disable_enabled_offline(lab, monkeypatch):
    import astropilot.field_lab_collection as collection
    calls = []
    monkeypatch.setattr(collection, 'launch_agents_path', lambda:collection.field_lab_root()/'launch-agents'/('test.plist'))
    collection.initialize()
    collection.scheduler('install', runner=lambda *a,**kw:pytest.fail('install is offline'))
    monkeypatch.setattr(collection.sys,'platform','darwin')
    def runner(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)
    collection.scheduler('disable', runner=runner)
    assert any(argv[1]=='bootout' for argv in calls)
    collection.scheduler('uninstall',runner=runner)
    assert not collection.scheduler_path().exists()


def test_initial_cycle_sync_and_capture_offline(lab, monkeypatch):
    import astropilot.field_lab_collection as collection
    collection.initialize()
    monkeypatch.setattr(collection, 'select_stations', lambda catalogue, ids=None:tuple(catalogue))
    calls = []
    client = SimpleNamespace(stations=lambda:calls.append('catalogue') or (STATION,),
        observations=lambda *a:pytest.fail('no window closed'))
    result = collection.cycle(lab, clock=lambda:T-timedelta(minutes=58), client=client,
                             capture=lambda station, hours:calls.append((station.station_id,hours)) or run())
    assert result['forecasts_created'] == 1 and calls == ['catalogue',('NEU',24)]
    assert len(lab.facts()[0]) == 1


def test_cycle_invalid_tolerance_before_network_or_creation(lab, tmp_path):
    from astropilot.field_lab_collection import cycle
    with pytest.raises(ValueError,match='tolerance'):
        cycle(lab,tolerance_minutes=-1)
    assert not (tmp_path/'lab').exists()


def test_status_and_bounded_failure_audit(lab, monkeypatch):
    import astropilot.field_lab_collection as collection
    collection.initialize()
    monkeypatch.setattr(collection,'now_utc',lambda:T)
    collection.record_error(RuntimeError('checksum_mismatch'))
    collection.record_error(RuntimeError('network_failure'))
    result = collection.status(lab)
    assert result['recent_errors'] == 1 and result['usage']['by_type']['collection_error'] == 1
    assert not result['scheduler']['installed']
    assert result['last_forecast'] is None


def test_empty_csv_has_stable_headers(lab, capsys):
    assert main(['report','--period','7d','--format','csv']) == 0
    assert capsys.readouterr().out.startswith('station,altitude_m,variable,unit,n_comparable,')


def test_cycle_lock_regular_file_and_concurrent_refusal(lab, tmp_path):
    from astropilot.field_lab_collection import initialize, cycle_lock
    initialize()
    with cycle_lock(lab):
        with cycle_lock(lab):
            pass  # nested operations share the outer writer transaction
    path = tmp_path/'lab'/'.writer.lock'
    path.unlink()
    path.symlink_to(tmp_path/'user')
    with pytest.raises(OSError):
        with cycle_lock(lab):
            pytest.fail('symlink lock admitted')
    assert not (tmp_path/'user').exists()


def test_failure_audit_does_not_initialize_an_absent_store(lab, tmp_path):
    from astropilot.field_lab_collection import record_error
    record_error(RuntimeError('initialization_required'))
    assert not (tmp_path/'lab').exists()
