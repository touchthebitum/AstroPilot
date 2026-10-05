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
    with pytest.raises(ValueError, match='artifact_limit'):
        lab.facts()


def test_hours_zero_rejected_before_store(monkeypatch, capsys):
    import astropilot.reference_station_cli as cli
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:pytest.fail('store constructed'))
    for options in ([], ['--dry-run']):
        assert main(['forecast-run', '--hours', '0', *options]) == 2
        assert 'reference_hours' in capsys.readouterr().err


def test_sync_identical_noop(lab, monkeypatch):
    import astropilot.reference_station_cli as cli
    monkeypatch.setattr(cli, 'ReferenceLab', lambda:lab)
    monkeypatch.setattr(cli, 'MeteoSwissReferenceClient', lambda:SimpleNamespace(stations=lambda:(STATION,)))
    assert main(['stations', 'sync', '--stations', 'NEU']) == 0
    assert main(['stations', 'sync', '--stations', 'NEU']) == 0
    assert len(tuple(lab.store.iter_artifacts())) == 1


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
