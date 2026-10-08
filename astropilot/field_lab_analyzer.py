"""Offline Field Lab analysis. No collector or production dependencies."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat

DOMAIN = 'field_lab_reference_station'
LIMIT = 16 * 1024 * 1024
KINDS = frozenset(('reference_observation', 'reference_acquisition', 'reference_forecast',
                  'reference_seal', 'reference_seal_completion', 'reference_seal_commit',
                  'collection_success', 'reference_comparison', 'reference_comparison_state',
                  'reference_report', 'reference_catalogue', 'catalog_activation_event',
                  'official_asset_activation'))
VARIABLES = {'temperature_2m': ('°C', 'tre200s0'),
             'relative_humidity_2m': ('%', 'ure200s0'),
             'wind_speed_10m': ('km/h', 'fu3010z0')}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def load_json(value):
    return json.loads(value, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def instant(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if d.tzinfo is None:
            raise ValueError()
        return d.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError('invalid_timestamp') from error


def stamp(value):
    return instant(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def valid_value(value, variable):
    if value is None:
        return True
    if not number(value):
        return False
    return (variable != 'temperature_2m' or -100 <= value <= 60) and (
        variable != 'relative_humidity_2m' or 0 <= value <= 100) and (
        variable != 'wind_speed_10m' or value >= 0)


@dataclass(frozen=True)
class SourceArtifact:
    path: str
    byte_sha256: str | None
    identity: str | None
    kind: str | None
    document: dict | None
    status: str
    issues: tuple[str, ...]
    schema_version: int = 1


@dataclass(frozen=True)
class NormalizedObservation:
    site: str
    source: str
    variable: str
    at_utc: str
    value: float | None
    unit: str
    quality: str | None
    evidence: tuple[str, ...]
    confidence: str = 'unknown'
    status: str = 'observed'
    priority: str | None = None
    schema_version: int = 1


@dataclass(frozen=True)
class ForecastPoint:
    run_id: str
    site: str
    provider: str | None
    model: str | None
    source: str
    variable: str
    at_utc: str
    value: float | None
    unit: str
    retrieved_at_utc: str
    created_at_utc: str
    sealed_at_utc: str | None
    prospective: bool | None
    evidence: tuple[str, ...]
    confidence: str = 'unknown'
    status: str = 'forecast'
    priority: str | None = None
    schema_version: int = 1


@dataclass(frozen=True)
class MatchedPair:
    forecast: ForecastPoint
    observation: NormalizedObservation | None
    offset_minutes: float | None
    signed_error: float | None
    reason: str
    status: str
    confidence: str
    priority: str | None = None
    schema_version: int = 1


@dataclass(frozen=True)
class MetricRecord:
    provider: str | None
    model: str | None
    site: str
    variable: str
    unit: str
    count: int
    mean_bias: float | None
    mae: float | None
    confidence: str = 'unverified'
    status: str = 'descriptive'
    priority: str | None = None
    schema_version: int = 1


@dataclass(frozen=True)
class ReportSummary:
    verdict: str
    coverage: list[dict]
    cycle_coverage: list[dict]
    distributions: list[dict]
    metrics: list[dict]
    pair_status: dict[str, int]
    limits: tuple[str, ...]
    schema_version: int = 1


def check_payload(d):
    p = d['payload']; kind = d['artifact_type']
    if 'schema_version' in p and (type(p['schema_version']) is not int or p['schema_version'] != 1):
        raise ValueError('unknown_schema')
    if kind in ('reference_acquisition', 'reference_observation'):
        required = ('station_id', 'source', 'variable', 'observed_at_utc', 'retrieved_at_utc',
                    'value', 'unit', 'quality', 'parameter', 'asset_href', 'schema_version')
        if not all(k in p for k in required):
            raise ValueError('missing_observation_fields')
        if p['station_id'] != d['source_id'] or p['source'] != 'MeteoSwiss':
            raise ValueError('invalid_observation_provenance')
        if p['variable'] not in VARIABLES or (p['unit'], p['parameter']) != VARIABLES[p['variable']]:
            raise ValueError('unknown_variable_contract')
        if instant(p['observed_at_utc']) > instant(p['retrieved_at_utc']):
            raise ValueError('future_observation')
        if not valid_value(p['value'], p['variable']):
            raise ValueError('invalid_value')
    elif kind == 'reference_forecast':
        s = load_json(p['snapshot_json'])
        if p['run_id'] != d['idempotency_key'] or p['run_id'] != digest({k:v for k,v in p.items() if k != 'run_id'}):
            raise ValueError('run_identity_mismatch')
        if s['station']['station_id'] != d['source_id']:
            raise ValueError('station_mismatch')
        if type(p.get('prospective')) is not bool:
            raise ValueError('missing_prospective')
        created = instant(p['created_at_utc']); retrieved = instant(p['forecast_retrieved_at_utc'])
        if retrieved > created or stamp(p['created_at_utc']) != stamp(d['created_at_utc']):
            raise ValueError('invalid_retrieval')
        if not isinstance(s.get('transport', {}).get('provider'), (str, type(None))) or not isinstance(s.get('model'), (str, type(None))):
            raise ValueError('invalid_provider_identity')
        times = []
        for point in s['points']:
            target = instant(point['at']); times.append(target)
            if p['prospective'] and max(created, retrieved) >= target:
                raise ValueError('leakage_detected')
            for v, x in point['values'].items():
                if v not in VARIABLES or s['units'].get(v) != VARIABLES[v][0] or not valid_value(x, v):
                    raise ValueError('unknown_variable_contract')
        if not times or times != sorted(set(times)):
            raise ValueError('invalid_forecast_sequence')
    elif kind == 'collection_success':
        if instant(p['at_utc']) > instant(p['completed_at_utc']):
            raise ValueError('invalid_cycle_time')


def scan(root):
    root = Path(root).resolve(strict=True)
    folder = root / 'artifacts'
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('artifacts_directory_required')
    paths = sorted(folder.iterdir(), key=lambda p:p.name)
    rows = []
    for path in paths:
        byte_sha = None; d = None; issues = []
        try:
            handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(handle, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError('regular_file_required')
                b = stream.read(LIMIT + 1)
                after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('input_changed')
            if not b or len(b) > LIMIT:
                raise ValueError('empty_or_oversized')
            byte_sha = hashlib.sha256(b).hexdigest(); d = load_json(b)
            if type(d) is not dict or type(d.get('payload')) is not dict:
                raise ValueError('invalid_document')
            if set(d) != {'artifact_type','schema_version','provenance','namespace',
                          'calibration_eligible','created_at_utc','source_id','idempotency_key','payload','digest'}:
                raise ValueError('unknown_envelope_fields')
            if type(d.get('schema_version')) is not int or d['schema_version'] != 1:
                raise ValueError('unknown_schema')
            if d.get('provenance') != DOMAIN or d.get('namespace') != DOMAIN:
                raise ValueError('missing_provenance')
            if d.get('calibration_eligible') is not False:
                raise ValueError('production_eligible_forbidden')
            for key in ('idempotency_key','source_id','artifact_type'):
                if not isinstance(d.get(key), str) or not d[key]:
                    raise ValueError('missing_identity')
            stamp(d['created_at_utc'])
            if digest(d['payload']) != d.get('digest'):
                raise ValueError('digest_mismatch')
            check_payload(d)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
            issues.append(str(error) if isinstance(error, ValueError) else type(error).__name__)
        kind = d.get('artifact_type') if isinstance(d, dict) else None
        identity = d.get('idempotency_key') if isinstance(d, dict) else None
        status = 'invalid' if issues else ('valid' if kind in KINDS else 'unsupported')
        rows.append(SourceArtifact(path.name, byte_sha, identity, kind, d, status, tuple(issues)))
    # Conflicting identity records cannot be rescued by deterministic ordering.
    by_id = defaultdict(list)
    for row in rows:
        if row.status == 'valid':
            by_id[row.identity].append(row)
    conflicts = {key for key, items in by_id.items() if len({canonical(x.document) for x in items}) > 1}
    rows = [SourceArtifact(x.path,x.byte_sha256,x.identity,x.kind,x.document,'invalid',('identity_conflict',))
            if x.identity in conflicts else x for x in rows]
    valid = [x for x in rows if x.status == 'valid']
    sizes = [len(canonical(x.document).encode()) for x in valid]
    counts = Counter(x.status for x in rows)
    summary = dict(schema_version=1, total=len(rows), valid=counts['valid'], invalid=counts['invalid'],
                   unsupported=counts['unsupported'], canonical_bytes=sum(sizes),
                   byte_duplicates=sum(n-1 for n in Counter(x.byte_sha256 for x in rows if x.byte_sha256).values()),
                   types=dict(sorted(Counter(x.kind or 'unknown' for x in rows).items())),
                   min_created=min((stamp(x.document['created_at_utc']) for x in valid),default=None),
                   max_created=max((stamp(x.document['created_at_utc']) for x in valid),default=None),
                   artifacts=[asdict(x) for x in rows])
    return rows, summary


def seal_chain(d, index):
    """Validate the causal publication receipts without invoking the writer."""
    p = d['payload']; run = p['run_id']; site = d['source_id']
    try:
        seal = index['seal-' + run]; commit = index['commit-' + run]
        cp = commit['payload']; candidate = index[cp['candidate_key']]
        sd = digest(load_json(p['snapshot_json']))
        if seal['artifact_type'] != 'reference_seal' or commit['artifact_type'] != 'reference_seal_commit' or candidate['artifact_type'] != 'reference_seal_completion':
            return None, ()
        if not cp['candidate_key'].startswith('candidate-' + run + '-'):
            return None, ()
        if any(x['source_id'] != site for x in (seal, commit, candidate)):
            return None, ()
        if seal['payload'] != dict(run_id=run, snapshot_digest=sd):
            return None, ()
        expected = dict(run_id=run, snapshot_digest=sd, seal_digest=seal['digest'])
        if candidate['payload'] != expected or cp != dict(expected, candidate_key=candidate['idempotency_key'], candidate_digest=digest(canonical(candidate))):
            return None, ()
        times = [instant(x['created_at_utc']) for x in (d,seal,candidate,commit)]
        if times != sorted(times):
            return None, ()
        return stamp(commit['created_at_utc']), tuple(x['idempotency_key'] for x in (seal,candidate,commit))
    except (KeyError, TypeError, ValueError):
        return None, ()


def normalize(rows):
    index = {x.identity:x.document for x in rows if x.status == 'valid'}
    observations = {}; forecasts = []
    for key in sorted(index):
        d = index[key]; p = d['payload']; kind = d['artifact_type']
        if kind in ('reference_observation','reference_acquisition'):
            identity = (p['station_id'],p['source'],p['variable'],stamp(p['observed_at_utc']),
                        p['value'],p['unit'],p['quality'])
            observations.setdefault(identity, []).append(key)
        elif kind == 'reference_forecast':
            snapshot = load_json(p['snapshot_json']); sealed, evidence = seal_chain(d,index)
            for point in snapshot['points']:
                for variable, value in sorted(point['values'].items()):
                    forecasts.append(ForecastPoint(key,d['source_id'],snapshot.get('transport',{}).get('provider'),
                        snapshot.get('model'),'MeteoSwiss',variable,stamp(point['at']),value,
                        snapshot['units'][variable],stamp(p['forecast_retrieved_at_utc']),
                        stamp(p['created_at_utc']),sealed,p.get('prospective'),(key,)+evidence))
    obs = [NormalizedObservation(*key,tuple(sorted(set(evidence))),
           confidence='unverified' if key[-1]=='unverified' else 'unknown')
           for key,evidence in observations.items()]
    return sorted(obs,key=lambda x:canonical(asdict(x))), sorted(forecasts,key=lambda x:canonical(asdict(x)))


def match(forecast, observations, tolerance):
    if not number(tolerance) or not 0 <= tolerance <= 60:
        raise ValueError('tolerance_0_to_60_minutes')
    target = instant(forecast.at_utc)
    candidates = [o for o in observations if (o.site,o.variable,o.source,o.unit)==
                  (forecast.site,forecast.variable,forecast.source,forecast.unit)]
    nearest = []
    if candidates:
        distance = min(abs((instant(o.at_utc)-target).total_seconds()) for o in candidates)
        nearest = [o for o in candidates if abs((instant(o.at_utc)-target).total_seconds())==distance]
    o = nearest[0] if len(nearest)==1 else None
    offset = (instant(o.at_utc)-target).total_seconds()/60 if o else None
    reason = 'missing_observation' if not nearest else 'ambiguous_observation'
    error = None
    if o:
        if abs(offset) > tolerance:
            reason = 'outside_tolerance'
        elif forecast.sealed_at_utc is None:
            reason = 'missing_durable_seal'
        elif forecast.prospective is not True:
            reason = 'nonprospective'
        elif max(instant(forecast.created_at_utc),instant(forecast.retrieved_at_utc),instant(forecast.sealed_at_utc)) >= min(target,instant(o.at_utc)):
            reason = 'leakage_detected'
        elif not forecast.provider:
            reason = 'missing_provider'
        elif o.quality != 'unverified' or not number(o.value) or not number(forecast.value):
            reason = 'unknown_or_invalid_observation'
        elif forecast.variable not in ('temperature_2m','relative_humidity_2m'):
            reason = 'aggregation_semantics_unverified'
        else:
            error = forecast.value-o.value; reason = 'comparable_unverified_official_qc'
    return MatchedPair(forecast,o,offset,error,reason,'comparable' if error is not None else 'non_comparable',
                       'unverified' if error is not None else 'unknown')


def grid(times, seconds):
    times = sorted(set(instant(t) for t in times))
    if not times:
        return dict(points=0,expected_slots=0,missing_slots=0,gap_rate=None,min=None,max=None)
    # The explicit grid is anchored to the first instant; off-grid times are disclosed.
    on_grid = [t for t in times if (t-times[0]).total_seconds() % seconds == 0]
    expected = int((times[-1]-times[0]).total_seconds()//seconds)+1
    missing = expected-len(on_grid)
    return dict(points=len(times),expected_slots=expected,missing_slots=missing,
                gap_rate=missing/expected,off_grid=len(times)-len(on_grid),
                min=stamp(times[0].isoformat()),max=stamp(times[-1].isoformat()))


def coverage(observations):
    groups = defaultdict(list)
    for o in observations:
        groups[(o.site,o.source,o.variable,o.unit)].append(o.at_utc)
    return [dict(site=k[0],source=k[1],variable=k[2],unit=k[3],**grid(ts,600)) for k,ts in sorted(groups.items())]


def report(rows, observations, forecasts, tolerance):
    groups = defaultdict(list)
    for o in observations:
        groups[(o.site,o.variable,o.source,o.unit,'observation')].append(o.value)
    for f in forecasts:
        groups[(f.site,f.variable,f.provider or 'unknown',f.unit,'forecast')].append(f.value)
    distributions=[]
    for k,values in sorted(groups.items()):
        nums=[v for v in values if number(v)]
        distributions.append(dict(site=k[0],variable=k[1],source=k[2],unit=k[3],kind=k[4],
              count=len(nums),missing=len(values)-len(nums),min=min(nums,default=None),max=max(nums,default=None),
              mean=sum(nums)/len(nums) if nums else None))
    by_measure = defaultdict(list)
    for o in observations:
        by_measure[(o.site,o.variable)].append(o)
    pairs = [match(f,by_measure[(f.site,f.variable)],tolerance) for f in forecasts]
    errors=defaultdict(list)
    for p in pairs:
        if p.signed_error is not None:
            f=p.forecast;errors[(f.provider,f.model,f.site,f.variable,f.unit)].append(p.signed_error)
    metrics=[asdict(MetricRecord(*k,len(es),sum(es)/len(es),sum(abs(e) for e in es)/len(es)))
             for k,es in sorted(errors.items(),key=lambda kv:canonical(kv[0]))]
    cycles = [x.document['payload']['at_utc'] for x in rows if x.status=='valid' and x.kind=='collection_success']
    summary = ReportSummary('USABLE_WITH_GAPS' if observations and forecasts else 'INSUFFICIENT',
              coverage(observations),[grid(cycles,3600)] if cycles else [],distributions,metrics,
              dict(sorted(Counter(p.reason for p in pairs).items())),
              ('Descriptive offline analysis only; no production policy changes.',
               'Official QC unknown; provider model may be unspecified.',
               'Wind aggregation unverified; excluded from errors.',
               'No NightMerit outcomes, OIII/Hα, Moon, transparency, seeing or AQI labels.',
               'Gap rates describe sampled instants, not scheduler failures.',
               'Forecast runs overlap; errors are not independent samples.'))
    return pairs,summary


def output_directory(raw, output):
    raw=Path(raw).resolve(strict=True); requested=Path(output)
    dest=requested.resolve()
    if dest==raw or raw in dest.parents or dest.parts[:2] in (('/', 'Volumes'),('/', 'share')):
        raise ValueError('local_output_outside_input_required')
    if requested.is_symlink() or requested.exists():
        raise ValueError('new_output_directory_required')
    # No existing symlink component is accepted, even when currently pointing locally.
    if any(p.is_symlink() for p in (requested,*requested.parents)):
        raise ValueError('output_symlink_forbidden')
    dest.mkdir(parents=True,exist_ok=False)
    return dest


def write_json(path,value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def write_lines(path,rows):
    path.write_text(''.join(canonical(asdict(row))+'\n' for row in rows),encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('scan','normalize','report'))
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--tolerance-minutes',type=float,default=10)
    args=parser.parse_args(argv)
    if not number(args.tolerance_minutes) or not 0 <= args.tolerance_minutes <= 60:
        raise ValueError('tolerance_0_to_60_minutes')
    # Validate destination before any output creation; scan reads raw only.
    raw=Path(args.input).resolve(strict=True); requested=Path(args.output)
    dest=requested.resolve()
    if dest==raw or raw in dest.parents or requested.exists() or requested.is_symlink() or any(p.is_symlink() for p in requested.parents) or dest.parts[:2] in (('/', 'Volumes'),('/', 'share')):
        raise ValueError('new_local_output_outside_input_required')
    rows,inventory=scan(raw)
    out=output_directory(raw,requested);write_json(out/'scan.json',inventory)
    if args.command!='scan':
        observations,forecasts=normalize(rows)
        write_lines(out/'observations.jsonl',observations);write_lines(out/'forecasts.jsonl',forecasts)
        if args.command=='report':
            pairs,summary=report(rows,observations,forecasts,args.tolerance_minutes)
            write_lines(out/'pairs.jsonl',pairs);write_json(out/'report.json',asdict(summary))
            text=['# Field Lab Analyzer v1', '', 'Verdict: '+summary.verdict,
                  f'Artifacts: {len(rows)}; observations: {len(observations)}; forecast values: {len(forecasts)}.',
                  '', 'Matching exclusions/counts: '+canonical(summary.pair_status),'',
                  '## Provider errors (forecast minus observation)', '',
                  '| Site | Provider | Variable | n | Bias | MAE |','|---|---|---|---:|---:|---:|']
            text += [f"| {m['site']} | {m['provider']} | {m['variable']} | {m['count']} | {m['mean_bias']:.6g} | {m['mae']:.6g} |" for m in summary.metrics]
            text += ['', '## Limits','']+['- '+limit for limit in summary.limits]
            (out/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
