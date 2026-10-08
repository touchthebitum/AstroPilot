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
    a.main(['report','--input',str(raw),'--output',str(tmp_path/'out')])
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


def test_matching_and_evidence_monotonicity():
    f=point();o=observation();p=a.match(f,[o],10)
    assert p.status=='comparable' and p.signed_error==2 and p.offset_minutes==0
    near=replace(o,at_utc='2026-10-08T10:05:00.000000Z')
    assert a.match(f,[near],10).offset_minutes==5
    assert a.match(f,[near],4).status=='non_comparable'
    for reduced in [replace(f,sealed_at_utc=None),replace(f,prospective=None)]:
        assert a.match(reduced,[o],10).status=='non_comparable'
    assert a.match(f,[],10).confidence=='unknown'
    assert a.match(f,[replace(o,quality=None)],10).status=='non_comparable'
    assert a.match(f,[near,replace(o,at_utc='2026-10-08T09:55:00.000000Z')],10).reason=='ambiguous_observation'
    assert a.match(f,[o,replace(o,value=9)],10).reason=='ambiguous_observation'
    assert a.match(replace(f,variable='wind_speed_10m'),[replace(o,variable='wind_speed_10m')],10).signed_error is None


def test_output_guards_and_determinism(tmp_path):
    raw=tmp_path/'raw';raw.mkdir();artifact(raw)
    with pytest.raises(ValueError):a.main(['scan','--input',str(raw),'--output',str(raw/'out')])
    for n in ['x','y']:a.main(['report','--input',str(raw),'--output',str(tmp_path/n)])
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
    obs,fs=a.normalize(a.scan(tmp_path)[0]);assert a.match(fs[0],obs,10).signed_error==2
    for prefix in ['seal-','candidate-','commit-']:
        rows=a.scan(tmp_path)[0]
        reduced=[r for r in rows if not r.identity.startswith(prefix)]
        obs,fs=a.normalize(reduced)
        assert a.match(fs[0],obs,10).reason=='missing_durable_seal'
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
