"""Internal field lab CLI; no scheduler, app factory or user store writes."""
import argparse
from dataclasses import asdict
import json
import sys

from astropilot.reference_station_lab import (
    MeteoSwissReferenceClient, ReferenceLab, ReferenceStation, capture_forecast,
    digest, now_utc, report, select_stations,
)


def parser():
    root = argparse.ArgumentParser(prog='astropilot-field-lab')
    commands = root.add_subparsers(dest='command', required=True)
    stations = commands.add_parser('stations').add_subparsers(dest='operation', required=True)
    sync = stations.add_parser('sync')
    listing = stations.add_parser('list')
    for item in (sync, listing):
        item.add_argument('--stations', help='Comma-separated official uppercase station IDs')
        item.add_argument('--all', action='store_true')
    forecast = commands.add_parser('forecast-run')
    forecast.add_argument('--stations')
    forecast.add_argument('--all', action='store_true')
    forecast.add_argument('--hours', type=int, default=24)
    forecast.add_argument('--dry-run', action='store_true')
    observations = commands.add_parser('observations').add_subparsers(dest='operation', required=True)
    collect = observations.add_parser('collect')
    compare = commands.add_parser('compare')
    summary = commands.add_parser('report')
    cycle = commands.add_parser('cycle')
    cycle.add_argument('--dry-run', action='store_true')
    summary.add_argument('--historical', action='store_true', help='Separate backfill cohort; never included by default')
    for item in (collect, compare, summary, cycle):
        item.add_argument('--tolerance-minutes', type=float, default=10)
    for item in (compare, summary):
        item.add_argument('--export', action='store_true', help='Save immutable JSON report in isolated Field Lab store')
    return root


def saved_catalogue(lab):
    activations = [a for a in lab.store.iter_artifacts(max_names=lab.max_artifacts)
                   if a.artifact_type == 'catalog_activation_event']
    if not activations:
        raise ValueError('reference_catalogue_missing_run_stations_sync')
    events = [(a, json.loads(a.payload_json)) for a in activations]
    from astropilot.reference_station_lab import canonical_utc
    for artifact, value in events:
        if (set(value) != {'catalogue_digest', 'retrieved_at_utc'}
                or canonical_utc(value['retrieved_at_utc']) != value['retrieved_at_utc']
                or artifact.created_at_utc != value['retrieved_at_utc']):
            raise ValueError('reference_catalog_activation_invalid')
    maximum = max(value['retrieved_at_utc'] for _, value in events)
    latest = [value for _, value in events if value['retrieved_at_utc'] == maximum]
    if len({value['catalogue_digest'] for value in latest}) != 1:
        raise ValueError('reference_catalogue_activation_ambiguous')
    event = latest[0]
    catalogue = lab.store.load(idempotency_key=event['catalogue_digest'])
    if (catalogue is None or catalogue.artifact_type != 'reference_catalogue'
            or catalogue.digest != event['catalogue_digest']):
        raise ValueError('reference_catalog_activation_mismatch')
    payload = json.loads(catalogue.payload_json)
    return tuple(ReferenceStation(**s) for s in payload['stations']), payload['active_station_ids']


def selection(args, catalogue, active):
    ids = args.stations.split(',') if args.stations else active
    return select_stations(catalogue, ids, all_stations=args.all)


def execute(args):
    if args.command == "forecast-run" and (type(args.hours) is not int or not 1 <= args.hours <= 168):
        raise ValueError("reference_hours_1_to_168")
    lab = ReferenceLab()  # Validates storage configuration/capabilities before network calls.
    if args.command == 'cycle' and args.dry_run:
        from astropilot.reference_station_lab import validate_tolerance
        validate_tolerance(args.tolerance_minutes)
        runs, _ = lab.facts()
        current = now_utc()
        return {'dry_run': True, 'network_calls': 0, 'writes': 0,
                'sealed_runs': len(runs), 'at_utc': current.isoformat(),
                'steps': ['collect_due_observations', 'compare', 'report'],
                'forecast_capture': 'explicit forecast-run required',
                'tolerance_minutes': args.tolerance_minutes}
    if args.command == 'stations':
        if args.operation == 'sync':
            catalogue = MeteoSwissReferenceClient().stations()
            ids = args.stations.split(',') if args.stations else None
            active = select_stations(catalogue, ids, all_stations=args.all)
            retrieved = now_utc().isoformat()
            payload = {'schema_version': 1, 'source': 'MeteoSwiss',
                       'collection': 'ch.meteoschweiz.ogd-smn',
                       'stations': [asdict(s) for s in catalogue],
                       'active_station_ids': [s.station_id for s in active],
                       'selection_version': 'smn-prospective-v1'}
            lab.save_catalogue(payload, retrieved)
            return {'catalogue_size': len(catalogue), 'active': [asdict(s) for s in active]}
        catalogue, active = saved_catalogue(lab)
        return [asdict(s) for s in selection(args, catalogue, active)]
    if args.command == 'forecast-run':
        catalogue, active = saved_catalogue(lab)
        stations = selection(args, catalogue, active)
        if args.dry_run:
            return {'dry_run': True, 'network_calls': 0, 'writes': 0,
                    'stations': [s.station_id for s in stations], 'hours': args.hours}
        results = []
        for station in stations:
            run = capture_forecast(station, hours=args.hours)
            lab.save_run(run)
            results.append({'station': station.station_id, 'run_id': run.run_id,
                            'snapshot_digest': run.snapshot_digest,
                            'targets': len(json.loads(run.snapshot_json)['points'])})
        return results
    if args.command == 'observations':
        return {'new_observations': lab.collect(MeteoSwissReferenceClient(),
                                               tolerance_minutes=args.tolerance_minutes)}
    if args.command == 'cycle':
        lab.collect(MeteoSwissReferenceClient(), tolerance_minutes=args.tolerance_minutes)
    comparisons = lab.comparisons(tolerance_minutes=args.tolerance_minutes,
                                 persist=args.command in ('compare', 'cycle'),
                                 historical=getattr(args, 'historical', False))
    runs, _ = lab.facts()
    rows = report(comparisons, runs)
    if getattr(args, 'export', False):
        payload = {'schema_version': 1, 'rows': rows}
        lab.save('reference_report', digest(payload), payload, now_utc().isoformat())
    return rows


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
