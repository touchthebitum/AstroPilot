import ast
import json
from dataclasses import replace
from pathlib import Path
import pytest
from astropilot import field_lab_analyzer as a


def artifact(root, payload=None, kind='reference_observation', key='one', **changes):
    p = payload or dict(schema_version=1, station_id='BAS', source='MeteoSwiss',
                       variable='temperature_2m', observed_at_utc='2026-10-08T10:00:00Z',
                       retrieved_at_utc='2026-10-08T11:00:00Z', value=10, unit='°C',
                       quality='unverified', parameter='tre200s0', asset_href='https://example.test')
    d = dict(schema_version=1, artifact_type=kind, source_id='BAS',
             created_at_utc='2026-10-08T11:00:00Z', idempotency_key=key,
             provenance=a.DOMAIN, namespace=a.DOMAIN, calibration_eligible=False,
             payload=p, digest=a.digest(p))
    d.update(changes)
    folder = root / 'artifacts'; folder.mkdir(exist_ok=True)
    (folder / (key + '.json')).write_text(a.canonical(d))
    return d


def test_valid_and_input_unchanged(tmp_path):
    raw=tmp_path/'raw';raw.mkdir();artifact(raw)
    before={p.name:p.read_bytes() for p in (raw/'artifacts').iterdir()}
    a.main(['scan','--input',str(raw),'--output',str(tmp_path/'baseline')])
    a.main(['report','--input',str(raw),'--output',str(tmp_path/'out'),
            '--inventory',str(tmp_path/'baseline'/'inventory.json')])
    assert before=={p.name:p.read_bytes() for p in (raw/'artifacts').iterdir()}
    assert json.loads((tmp_path/'out'/'scan.json').read_text())['valid']==1


@pytest.mark.parametrize('change,issue', [({'schema_version':2},'unknown_schema'),
 ({'provenance':None},'missing_provenance'),({'created_at_utc':'2026-10-08T10:00:00'},'invalid_timestamp'),
 ({'created_at_utc':'bad'},'invalid_timestamp'),({'digest':'bad'},'digest_mismatch')])
def test_invalid(tmp_path,change,issue):
    artifact(tmp_path,**change)
    assert issue in a.scan(tmp_path)[0][0].issues


def test_corrupt_and_unknown(tmp_path):
    folder=tmp_path/'artifacts';folder.mkdir();(folder/'bad.json').write_bytes(b'\xff')
    assert a.scan(tmp_path)[0][0].status=='invalid'
    artifact(tmp_path,kind='future_kind')
    assert any(x.status=='unsupported' for x in a.scan(tmp_path)[0])


def test_duplicates_and_gaps(tmp_path):
    d=artifact(tmp_path);artifact(tmp_path,payload=d['payload'],key='two',kind='reference_acquisition')
    obs,_=a.normalize(a.scan(tmp_path)[0]);assert len(obs)==1 and len(obs[0].evidence)==2
    late=replace(obs[0],at_utc='2026-10-08T10:30:00.000000Z')
    assert a.coverage([obs[0],late])[0]['missing_slots']==2


def point():
    return a.ForecastPoint('run','BAS','Open-Meteo','unknown','MeteoSwiss','temperature_2m',
          '2026-10-08T10:00:00.000000Z',12,'°C','2026-10-08T09:00:00.000000Z',
          '2026-10-08T09:00:00.000000Z','2026-10-08T09:01:00.000000Z',True,('f','s','c','commit'))


def observation():
    return a.NormalizedObservation('BAS','MeteoSwiss','temperature_2m',
          '2026-10-08T10:00:00.000000Z',10,'°C','unverified',('obs',))


def verified_match(forecast, observations, tolerance):
    # Unit matching checks operate inside an already verified inventory boundary.
    return a.match(forecast, observations, tolerance, evidence_complete=True)


def test_matching_and_evidence_monotonicity():
    f=point();o=observation();p=verified_match(f,[o],10)
    assert p.status=='comparable' and p.signed_error==2 and p.offset_minutes==0
    near=replace(o,at_utc='2026-10-08T10:05:00.000000Z')
    assert verified_match(f,[near],10).offset_minutes==-5
    assert verified_match(f,[near],4).status=='non_comparable'
    for reduced in [replace(f,sealed_at_utc=None),replace(f,prospective=None)]:
        assert verified_match(reduced,[o],10).status=='non_comparable'
    assert verified_match(f,[],10).confidence=='unknown'
    assert verified_match(f,[replace(o,quality=None)],10).status=='non_comparable'
    assert verified_match(f,[near,replace(o,at_utc='2026-10-08T09:55:00.000000Z')],10).reason=='ambiguous_observation'
    assert verified_match(f,[o,replace(o,value=9)],10).reason=='ambiguous_observation'
    assert verified_match(replace(f,variable='wind_speed_10m'),[replace(o,variable='wind_speed_10m')],10).signed_error is None


def test_output_guards_and_determinism(tmp_path):
    raw=tmp_path/'raw';raw.mkdir();artifact(raw)
    with pytest.raises(ValueError):a.main(['scan','--input',str(raw),'--output',str(raw/'out')])
    a.main(['scan','--input',str(raw),'--output',str(tmp_path/'baseline')])
    for n in ['x','y']:
        a.main(['report','--input',str(raw),'--output',str(tmp_path/n),
                '--inventory',str(tmp_path/'baseline'/'inventory.json')])
    assert {p.name:p.read_bytes() for p in (tmp_path/'x').iterdir()}=={p.name:p.read_bytes() for p in (tmp_path/'y').iterdir()}
    link=tmp_path/'link';link.symlink_to(raw,target_is_directory=True)
    with pytest.raises(ValueError):a.main(['scan','--input',str(raw),'--output',str(link/'out')])


def test_no_network_or_production_imports():
    tree=ast.parse(Path(a.__file__).read_text());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(x.name.split('.')[0] for x in node.names)
        elif isinstance(node,ast.ImportFrom):imports.append(node.module.split('.')[0])
    assert set(imports)<= {'argparse','collections','dataclasses','datetime','hashlib','json','math','os','pathlib','stat'}


def sealed_forecast(root):
    snapshot=dict(station={'station_id':'BAS'},transport={'provider':'Open-Meteo'},model=None,
        units={'temperature_2m':'°C'},points=[{'at':'2026-10-08T10:00:00Z','values':{'temperature_2m':12}}])
    p=dict(schema_version=1,station_id='BAS',snapshot_json=a.canonical(snapshot),code_sha='abc',
        code_version='v1',prospective=True,created_at_utc='2026-10-08T09:00:00Z',
        forecast_retrieved_at_utc='2026-10-08T09:00:00Z')
    p['run_id']=a.digest(p); run=p['run_id'];sd=a.digest(snapshot)
    artifact(root,p,'reference_forecast',run,created_at_utc=p['created_at_utc'])
    s=artifact(root,dict(run_id=run,snapshot_digest=sd),'reference_seal','seal-'+run,
        created_at_utc='2026-10-08T09:00:01Z')
    c=artifact(root,dict(run_id=run,snapshot_digest=sd,seal_digest=s['digest']),
        'reference_seal_completion','candidate-'+run+'-abc',created_at_utc='2026-10-08T09:00:02Z')
    artifact(root,dict(run_id=run,snapshot_digest=sd,seal_digest=s['digest'],
        candidate_key=c['idempotency_key'],candidate_digest=a.digest(a.canonical(c))),
        'reference_seal_commit','commit-'+run,created_at_utc='2026-10-08T09:00:03Z')
    return run


def test_real_seal_chain_and_removal(tmp_path):
    run=sealed_forecast(tmp_path);artifact(tmp_path)
    obs,fs=a.normalize(a.scan(tmp_path)[0]);assert verified_match(fs[0],obs,10).signed_error==2
    for prefix in ['seal-','candidate-','commit-']:
        rows=a.scan(tmp_path)[0]
        reduced=[r for r in rows if not r.identity.startswith(prefix)]
        obs,fs=a.normalize(reduced)
        assert verified_match(fs[0],obs,10).reason=='missing_durable_seal'
    rows=a.scan(tmp_path)[0]
    altered=[]
    for row in rows:
        if row.kind=='reference_seal_commit':
            d=dict(row.document);d['payload']=dict(d['payload'],candidate_digest='bad')
            altered.append(replace(row,document=d))
        else:altered.append(row)
    obs,fs=a.normalize(altered);assert fs[0].sealed_at_utc is None


def test_missing_value_timezone_and_symlink(tmp_path):
    d=artifact(tmp_path);p=dict(d['payload'],value=None,quality='missing')
    artifact(tmp_path,payload=p,key='missing')
    obs,_=a.normalize(a.scan(tmp_path)[0]);assert any(o.value is None and o.quality=='missing' for o in obs)
    assert a.stamp('2026-10-08T12:00:00+02:00')==a.stamp('2026-10-08T10:00:00Z')
    (tmp_path/'artifacts'/'link.json').symlink_to(tmp_path/'artifacts'/'one.json')
    assert next(r for r in a.scan(tmp_path)[0] if r.path=='link.json').status=='invalid'


def test_duplicate_fields_identity_conflict_and_unknown_payload(tmp_path):
    d=artifact(tmp_path)
    (tmp_path/'artifacts'/'duplicate.json').write_text('{"schema_version":1,"schema_version":1}')
    assert 'duplicate_json_key' in next(r for r in a.scan(tmp_path)[0] if r.path=='duplicate.json').issues
    artifact(tmp_path,payload=dict(d['payload'],schema_version=2),key='future')
    assert next(r for r in a.scan(tmp_path)[0] if r.identity=='future').status=='invalid'
    other=dict(d,payload=dict(d['payload'],value=20));other['digest']=a.digest(other['payload'])
    (tmp_path/'artifacts'/'conflict.json').write_text(a.canonical(other))
    assert all(r.status=='invalid' for r in a.scan(tmp_path)[0] if r.identity=='one')


def test_zero_usable_pairs_is_insufficient(tmp_path):
    sealed_forecast(tmp_path)
    artifact(tmp_path, payload=dict(schema_version=1, station_id='BAS', source='MeteoSwiss',
        variable='temperature_2m', observed_at_utc='2026-10-08T10:00:00Z',
        retrieved_at_utc='2026-10-08T11:00:00Z', value=None, unit='°C',
        quality='missing', parameter='tre200s0', asset_href='https://example.test'))
    rows, _ = a.scan(tmp_path)
    pairs, summary = a.report(rows, 10, inventory=a.inventory_manifest(rows))
    assert summary.inventory_status == 'verified'
    assert summary.verdict == 'INSUFFICIENT' and summary.metrics == []
    assert len(pairs) == 1 and pairs[0].signed_error is None
    assert summary.pair_status == {'unknown_or_invalid_observation': 1}


def test_inventory_prevents_favorable_revision_removal(tmp_path):
    sealed_forecast(tmp_path)
    d = artifact(tmp_path)
    artifact(tmp_path, payload=dict(d['payload'], value=9), key='revision')
    rows, _ = a.scan(tmp_path)
    manifest = a.inventory_manifest(rows)
    pairs, summary = a.report(rows, 10, inventory=manifest)
    assert pairs[0].reason == 'ambiguous_observation'
    assert summary.verdict == 'INSUFFICIENT'
    (tmp_path/'artifacts'/'revision.json').unlink()
    reduced, _ = a.scan(tmp_path)
    pairs, summary = a.report(reduced, 10, inventory=manifest)
    assert summary.inventory_status == 'changed'
    assert summary.verdict == 'INSUFFICIENT' and summary.metrics == []
    assert pairs[0].reason == 'unverified_evidence_inventory'
    assert pairs[0].confidence == 'unknown' and pairs[0].signed_error is None


@pytest.mark.parametrize('change', ['removed', 'renamed', 'changed', 'added'])
def test_inventory_changes_block_metrics(tmp_path, change):
    sealed_forecast(tmp_path)
    d = artifact(tmp_path)
    rows, _ = a.scan(tmp_path)
    manifest = a.inventory_manifest(rows)
    pairs, summary = a.report(rows, 10, inventory=manifest)
    assert summary.verdict == 'USABLE_WITH_GAPS' and summary.metrics[0]['count'] == 1
    assert pairs[0].signed_error == 2
    path = tmp_path/'artifacts'/'one.json'
    if change == 'removed':
        path.unlink()
    elif change == 'renamed':
        path.rename(path.with_name('renamed.json'))
    elif change == 'changed':
        artifact(tmp_path, payload=dict(d['payload'], value=9))
    else:
        artifact(tmp_path, payload=d['payload'], key='duplicate')
    rows, _ = a.scan(tmp_path)
    pairs, summary = a.report(rows, 10, inventory=manifest)
    assert summary.inventory_status == 'changed' and summary.metrics == []
    assert summary.verdict == 'INSUFFICIENT'
    assert all(p.status == 'non_comparable' and p.signed_error is None for p in pairs)


def test_missing_inventory_cannot_authorize_metrics(tmp_path):
    sealed_forecast(tmp_path); artifact(tmp_path)
    rows, _ = a.scan(tmp_path)
    pairs, summary = a.report(rows, 10)
    assert summary.inventory_status == 'missing' and summary.metrics == []
    assert pairs[0].reason == 'unverified_evidence_inventory'
    assert a.match(point(), [observation()], 10).signed_error is None
    with pytest.raises(SystemExit):
        a.main(['report', '--input', str(tmp_path), '--output', str(tmp_path/'out')])
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('manifest', [[], {},
    {'schema_version': True, 'kind': 'field_lab_inventory', 'artifacts': []},
    {'schema_version': 1, 'kind': 'field_lab_inventory', 'artifacts': [
        {'path': '../outside', 'byte_sha256': None}]},
    {'schema_version': 1, 'kind': 'field_lab_inventory', 'artifacts': [
        {'path': 'one.json', 'byte_sha256': 'bad'}]},
    {'schema_version': 1, 'kind': 'field_lab_inventory', 'artifacts': [
        {'path': 'one.json', 'byte_sha256': None}, {'path': 'one.json', 'byte_sha256': None}]}])
def test_malformed_inventory_rejected(manifest):
    with pytest.raises(ValueError, match='invalid_inventory_manifest'):
        a.inventory_status([], manifest)


@pytest.mark.parametrize('field,value', [
    ('transport', []), ('transport', None), ('station', []), ('units', []),
    ('points', {}), ('points', [[]]),
    ('points', [{'at': '2026-10-08T10:00:00Z', 'values': []}])])
def test_malformed_forecast_isolated_by_scan(tmp_path, field, value):
    run = sealed_forecast(tmp_path)
    path = tmp_path/'artifacts'/(run+'.json')
    d = json.loads(path.read_text()); p = d['payload']
    snapshot = json.loads(p['snapshot_json']); snapshot[field] = value
    p['snapshot_json'] = a.canonical(snapshot)
    p['run_id'] = a.digest({k:v for k,v in p.items() if k != 'run_id'})
    d['idempotency_key'] = p['run_id']; d['digest'] = a.digest(p)
    path.write_text(a.canonical(d))
    artifact(tmp_path)
    rows, inventory = a.scan(tmp_path)
    bad = next(r for r in rows if r.kind == 'reference_forecast')
    assert bad.status == 'invalid' and bad.issues == ('invalid_forecast_structure',)
    assert next(r for r in rows if r.identity == 'one').status == 'valid'
    assert inventory['invalid'] == 1


@pytest.mark.parametrize('kind', ['reference_comparison', 'reference_comparison_state', 'reference_report'])
def test_stored_derivatives_are_indexed_without_scientific_validation(tmp_path, kind):
    sealed_forecast(tmp_path); artifact(tmp_path)
    artifact(tmp_path, payload={'arithmetic': 'unchecked', 'forecast_digest': 'unknown'},
             kind=kind, key='stored')
    rows, inventory = a.scan(tmp_path)
    stored = next(r for r in rows if r.identity == 'stored')
    assert stored.status == 'unsupported' and stored.document['payload']['arithmetic'] == 'unchecked'
    assert inventory['unsupported'] == 1
    pairs, summary = a.report(rows, 10, inventory=a.inventory_manifest(rows))
    assert len(pairs) == 1 and pairs[0].signed_error == 2
    assert summary.metrics[0]['count'] == 1


@pytest.mark.parametrize('at,offset', [
    ('2026-10-08T09:55:00Z', 5), ('2026-10-08T10:05:00Z', -5)])
def test_offset_is_target_minus_observation(at, offset):
    pair = verified_match(point(), [replace(observation(), at_utc=at)], 10)
    assert pair.offset_minutes == offset and pair.signed_error == 2


@pytest.mark.parametrize('eligible', [True, None, 0, 'false'])
def test_calibration_remains_forbidden(tmp_path, eligible):
    artifact(tmp_path, calibration_eligible=eligible)
    assert a.scan(tmp_path)[0][0].issues == ('production_eligible_forbidden',)


def test_cli_reduced_export_keeps_raw_bytes_and_blocks_all_metrics(tmp_path):
    raw = tmp_path/'raw'; raw.mkdir()
    sealed_forecast(raw); d = artifact(raw)
    artifact(raw, payload=dict(d['payload'], value=9), key='revision')
    baseline = tmp_path/'baseline'
    a.main(['scan', '--input', str(raw), '--output', str(baseline)])
    manifest_path = baseline/'inventory.json'
    original_manifest = manifest_path.read_bytes()
    (raw/'artifacts'/'revision.json').unlink()
    remaining = {p.name: p.read_bytes() for p in (raw/'artifacts').iterdir()}
    out = tmp_path/'out'
    a.main(['report', '--input', str(raw), '--output', str(out),
            '--inventory', str(manifest_path)])
    result = json.loads((out/'report.json').read_text())
    assert result['inventory_status'] == 'changed' and result['verdict'] == 'INSUFFICIENT'
    assert result['metrics'] == []
    pair = json.loads((out/'pairs.jsonl').read_text())
    assert pair['reason'] == 'unverified_evidence_inventory' and pair['signed_error'] is None
    assert 'Evidence inventory: changed' in (out/'report.md').read_text()
    assert json.loads((out/'inventory.json').read_text()) == json.loads(original_manifest)
    assert remaining == {p.name: p.read_bytes() for p in (raw/'artifacts').iterdir()}
    assert original_manifest == manifest_path.read_bytes()


@pytest.mark.parametrize('field', ['artifact_type', 'idempotency_key'])
def test_malformed_envelope_identity_does_not_interrupt_inventory(tmp_path, field):
    artifact(tmp_path, **{field: []})
    rows, summary = a.scan(tmp_path)
    assert rows[0].status == 'invalid' and summary['invalid'] == 1
