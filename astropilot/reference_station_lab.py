"""Prospective, immutable reference station lab. No user application composition."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import json
import math
import re
import statistics
import subprocess
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from astropilot.field_lab_store import FieldLabArtifact, FileFieldLabStore
from decision.weather.meteoswiss_acquisition import (
    decode_meteoswiss_csv, download_meteoswiss_observation_asset,
    fetch_meteoswiss_observation_asset,
)
from decision.weather.meteoswiss_assets import (
    METEOSWISS_OBSERVATION_COLLECTION, MeteoSwissGranularity, MeteoSwissProductFamily,
)
from decision.weather.meteoswiss_parsing import parse_meteoswiss_station_metadata_csv

BASE = 'https://data.geo.admin.ch/' + METEOSWISS_OBSERVATION_COLLECTION
# Official instantaneous 2m quantities; wind is captured but not compared.
VARIABLES = {
    'temperature_2m': ('tre200s0', '°C', -100, 60),
    'relative_humidity_2m': ('ure200s0', '%', 0, 100),
    'wind_speed_10m': ('fu3010z0', 'km/h', 0, None),
}
POLICY = 'nearest-unique-no-interpolation-v1'


def now_utc():
    return datetime.now(timezone.utc)


def utc(value):
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError('reference_utc_required')
    return stamp


def canonical_utc(value):
    return utc(value).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_domain(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == 'snapshot_json':
                result[key] = json.dumps(canonical_domain(json.loads(item)),
                    sort_keys=True, separators=(',', ':'), allow_nan=False)
            elif (key.endswith('_at_utc') or key == 'at') and item is not None:
                result[key] = canonical_utc(item)
            else:
                result[key] = canonical_domain(item)
        return result
    if isinstance(value, (list, tuple)):
        return [canonical_domain(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(canonical_domain(value), sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def station_identity(value):
    if not isinstance(value, str) or re.fullmatch('[A-Z]{3}', value) is None:
        raise ValueError('invalid_reference_station')


def numeric(value, variable):
    _, _, lower, upper = VARIABLES[variable]
    return (type(value) in (int, float) and math.isfinite(value)
            and value >= lower and (upper is None or value <= upper))


@dataclass(frozen=True)
class ReferenceStation:
    station_id: str
    name: str
    latitude: float
    longitude: float
    altitude_m: float
    parameters: tuple[str, ...]
    metadata_digest: str
    timezone: str = 'Europe/Zurich'
    source: str = 'MeteoSwiss'
    schema_version: int = 1

    def __post_init__(self):
        station_identity(self.station_id)
        if (self.source != 'MeteoSwiss' or type(self.schema_version) is not int or self.schema_version != 1
                or not self.name
                or not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180
                or not math.isfinite(self.altitude_m)):
            raise ValueError('invalid_reference_station_metadata')
        ZoneInfo(self.timezone)
        object.__setattr__(self, 'parameters', tuple(self.parameters))


@dataclass(frozen=True)
class ReferenceForecastRun:
    run_id: str
    station_id: str
    created_at_utc: str
    forecast_retrieved_at_utc: str
    snapshot_json: str
    code_sha: str
    code_version: str
    prospective: bool = True
    schema_version: int = 1

    def __post_init__(self):
        station_identity(self.station_id)
        for name in ("created_at_utc", "forecast_retrieved_at_utc"):
            object.__setattr__(self, name, canonical_utc(getattr(self, name)))
        object.__setattr__(self, "snapshot_json", json.dumps(canonical_domain(json.loads(self.snapshot_json)), sort_keys=True, separators=(",", ":"), allow_nan=False))
        created, retrieved = utc(self.created_at_utc), utc(self.forecast_retrieved_at_utc)
        snapshot = json.loads(self.snapshot_json)
        if type(self.schema_version) is not int or self.schema_version != 1 or type(self.prospective) is not bool:
            raise ValueError('invalid_reference_run')
        station = ReferenceStation(**snapshot['station'])
        transport = snapshot['transport']
        if (station.station_id != self.station_id
                or transport['requested_latitude'] != station.latitude
                or transport['requested_longitude'] != station.longitude
                or not transport['provider']
                or snapshot['units'] != {v: unit for v, (_, unit, _, _) in VARIABLES.items()}):
            raise ValueError('invalid_reference_snapshot_contract')
        if retrieved > created or not snapshot['points']:
            raise ValueError('invalid_reference_retrieval')
        for point in snapshot['points']:
            target = utc(point['at'])
            if self.prospective and (created >= target or retrieved >= target):
                raise ValueError('leakage_detected')
            if set(point['values']) != set(VARIABLES):
                raise ValueError('invalid_reference_variables')
            for variable, value in point['values'].items():
                if not numeric(value, variable):
                    raise ValueError('invalid_reference_forecast_value')
        times = [utc(point['at']) for point in snapshot['points']]
        if times != sorted(set(times)):
            raise ValueError('invalid_reference_forecast_times')
        if self.run_id != digest(self.identity()):
            raise ValueError('reference_run_digest_mismatch')

    def identity(self):
        return {k: v for k, v in asdict(self).items() if k != 'run_id'}

    @property
    def snapshot_digest(self):
        return digest(json.loads(self.snapshot_json))


@dataclass(frozen=True)
class ReferenceObservation:
    station_id: str
    observed_at_utc: str
    variable: str
    value: float | None
    unit: str
    retrieved_at_utc: str
    quality: str
    parameter: str
    asset_href: str
    source: str = 'MeteoSwiss'
    schema_version: int = 1

    def __post_init__(self):
        station_identity(self.station_id)
        for name in ("observed_at_utc", "retrieved_at_utc"):
            object.__setattr__(self, name, canonical_utc(getattr(self, name)))
        if self.variable not in VARIABLES:
            raise ValueError("invalid_reference_variable")
        if utc(self.observed_at_utc) > utc(self.retrieved_at_utc):
            raise ValueError('future_reference_observation')
        expected, unit, _, _ = VARIABLES[self.variable]
        if (self.source != 'MeteoSwiss' or type(self.schema_version) is not int or self.schema_version != 1
                or self.unit != unit or self.parameter != expected
                or self.quality not in ('unverified', 'missing', 'invalid_qc', 'invalid_value')
                or (self.value is not None and not numeric(self.value, self.variable))):
            raise ValueError('invalid_reference_observation')
        if self.quality == 'unverified' and self.value is None:
            raise ValueError('invalid_reference_unverified_missing_value')
        if self.quality != 'unverified' and self.value is not None:
            raise ValueError('invalid_reference_missing_value')

    @property
    def acquisition_id(self):
        return digest({"measurement_digest": self.measurement_digest,
                       "retrieved_at_utc": self.retrieved_at_utc})

    @property
    def measurement_digest(self):
        # Canonical content is independent of acquisition history.
        return digest({k: v for k, v in asdict(self).items()
                       if k not in ('retrieved_at_utc', 'asset_href')})


@dataclass(frozen=True)
class ReferenceComparison:
    forecast_run_id: str
    station_id: str
    variable: str
    forecast_point_at_utc: str
    observation_at_utc: str | None
    temporal_offset_minutes: float | None
    forecast_value: float | None
    observed_value: float | None
    signed_error: float | None
    absolute_error: float | None
    status: str
    reason: str
    forecast_digest: str
    observation_digest: str | None
    tolerance_minutes: float
    policy: str = POLICY
    source: str = 'MeteoSwiss'
    cohort: str = 'prospective'
    schema_version: int = 1

    def __post_init__(self):
        station_identity(self.station_id)
        if (type(self.schema_version) is not int or self.schema_version != 1
                or self.source != 'MeteoSwiss' or self.policy != POLICY
                or self.cohort not in ('prospective', 'historical_backfill')
                or self.variable not in VARIABLES
                or re.fullmatch('[0-9a-f]{64}', self.forecast_run_id or '') is None
                or re.fullmatch('[0-9a-f]{64}', self.forecast_digest or '') is None):
            raise ValueError('invalid_reference_comparison')
        validate_tolerance(self.tolerance_minutes)
        utc(self.forecast_point_at_utc)
        for name in ('forecast_point_at_utc', 'observation_at_utc'):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, canonical_utc(getattr(self, name)))
        if self.observation_at_utc is None:
            if self.temporal_offset_minutes is not None or self.observation_digest is not None:
                raise ValueError('invalid_reference_comparison_observation')
        else:
            expected = (utc(self.forecast_point_at_utc)-utc(self.observation_at_utc)).total_seconds()/60
            if (type(self.temporal_offset_minutes) not in (int, float)
                    or not math.isfinite(self.temporal_offset_minutes)
                    or not math.isclose(self.temporal_offset_minutes, expected, abs_tol=1e-9)
                    or re.fullmatch('[0-9a-f]{64}', self.observation_digest or '') is None):
                raise ValueError('invalid_reference_comparison_offset')
        if self.status == 'comparable':
            if (self.reason != 'comparable_unverified_official_qc'
                    or self.variable == 'wind_speed_10m' or self.observation_at_utc is None
                    or abs(self.temporal_offset_minutes) > self.tolerance_minutes
                    or not numeric(self.forecast_value, self.variable)
                    or not numeric(self.observed_value, self.variable)
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           for v in (self.signed_error, self.absolute_error))
                    or not math.isclose(self.signed_error, self.forecast_value-self.observed_value, rel_tol=1e-12, abs_tol=1e-9)
                    or not math.isclose(self.absolute_error, abs(self.signed_error), rel_tol=1e-12, abs_tol=1e-9)):
                raise ValueError('invalid_reference_comparison_arithmetic')
        elif self.status == 'non_comparable':
            reasons = {'missing_observation', 'ambiguous_nearest_observation', 'leakage_detected',
                       'outside_time_tolerance', 'missing', 'invalid_qc', 'invalid_value',
                       'aggregation_semantics_unverified', 'missing_durable_seal'}
            if self.reason not in reasons or any(v is not None for v in
                    (self.forecast_value, self.observed_value, self.signed_error, self.absolute_error)):
                raise ValueError('invalid_reference_comparison_status')
            if (self.reason in ('missing_observation', 'ambiguous_nearest_observation')) != (self.observation_at_utc is None):
                raise ValueError('invalid_reference_comparison_reason')
            if (self.reason == 'outside_time_tolerance' and abs(self.temporal_offset_minutes) <= self.tolerance_minutes
                    or self.reason == 'aggregation_semantics_unverified' and self.variable != 'wind_speed_10m'):
                raise ValueError('invalid_reference_comparison_reason')
        else:
            raise ValueError('invalid_reference_comparison_status')


def csv_rows(text, required):
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not set(required) <= set(reader.fieldnames)):
        raise ValueError('reference_csv_columns')
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('reference_csv_row_shape')
    return rows


class MeteoSwissReferenceClient:
    """Read-only injectable session. Official metadata CSV + checked STAC assets."""
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def metadata(self, name):
        url = f'{BASE}/ogd-smn_meta_{name}.csv'
        response = self.session.get(url, timeout=(5, 30), allow_redirects=False)
        try:
            if response.status_code != 200 or len(response.content) > 10_000_000:
                raise ValueError('reference_metadata_unavailable')
            return decode_meteoswiss_csv(response.content)
        finally:
            response.close()

    def stations(self):
        texts = {name: self.metadata(name) for name in ('stations', 'parameters', 'datainventory')}
        parameters = csv_rows(texts['parameters'], ('parameter_shortname', 'parameter_unit', 'parameter_granularity'))
        for parameter, unit, _, _ in VARIABLES.values():
            found = [p for p in parameters if p['parameter_shortname'] == parameter]
            if len(found) != 1 or found[0]['parameter_unit'] != unit or found[0]['parameter_granularity'] != 'T':
                raise ValueError('reference_parameter_contract_changed')
        inventory = csv_rows(texts['datainventory'], ('station_abbr', 'parameter_shortname', 'data_till'))
        available = {}
        for row in inventory:
            if not row['data_till'].strip():
                available.setdefault(row['station_abbr'], set()).add(row['parameter_shortname'])
        names = {row['station_abbr']: row['station_name'] for row in
                 csv_rows(texts['stations'], ('station_abbr', 'station_name'))}
        metadata_digest = digest(texts)
        from decision.location.location_time import LocationTimeResolver
        stations = [ReferenceStation(s.station_id, names[s.station_id], s.latitude, s.longitude,
                                    s.altitude_m, tuple(sorted(available.get(s.station_id, ()))),
                                    metadata_digest, timezone=LocationTimeResolver.resolve(s.latitude, s.longitude).timezone_name)
                    for s in parse_meteoswiss_station_metadata_csv(texts['stations'])
                    if s.altitude_m is not None]
        if len({s.station_id for s in stations}) != len(stations):
            raise ValueError('duplicate_reference_station')
        return tuple(sorted(stations, key=lambda s: s.station_id))

    def observations(self, station_id, family, *, retrieved_at=None):
        asset = fetch_meteoswiss_observation_asset(
            station_id.lower(), granularity=MeteoSwissGranularity.TEN_MINUTES,
            product_family=MeteoSwissProductFamily(family), session=self.session)
        downloaded = download_meteoswiss_observation_asset(asset, session=self.session)
        return parse_observations(decode_meteoswiss_csv(downloaded.content), station_id,
                                  retrieved_at or now_utc(), asset.href)


def parse_observations(text, station_id, retrieved_at, href):
    retrieved_at = utc(retrieved_at)
    rows = csv_rows(text, ('station_abbr', 'reference_timestamp'))
    result = []
    seen = set()
    for row in rows:
        if row['station_abbr'] != station_id:
            raise ValueError('reference_station_mismatch')
        observed = datetime.strptime(row['reference_timestamp'], '%d.%m.%Y %H:%M').replace(tzinfo=timezone.utc)
        if observed in seen:
            raise ValueError('duplicate_reference_timestamp')
        seen.add(observed)
        if observed > retrieved_at:
            continue
        for variable, (parameter, unit, _, _) in VARIABLES.items():
            raw = row.get(parameter, '').strip()
            quality, value = 'unverified', None
            if not raw:
                quality = 'missing'
            else:
                try:
                    value = float(raw)
                except ValueError:
                    quality = 'invalid_value'
                if value is not None and not numeric(value, variable):
                    quality, value = 'invalid_value', None
            # Current official CSV has no QC columns. Unknown supplied QC fails closed.
            qc = row.get(parameter + '_qc', '').strip()
            if qc:
                quality, value = 'invalid_qc', None
            result.append(ReferenceObservation(station_id, observed.isoformat(), variable,
                          value, unit, retrieved_at.isoformat(), quality, parameter, href))
    return tuple(result)


def select_stations(stations, ids=None, *, all_stations=False):
    eligible = {s.station_id: s for s in stations
                if all(p in s.parameters for p, *_ in VARIABLES.values())}
    if all_stations:
        return tuple(eligible[k] for k in sorted(eligible))
    if ids is None:
        config = json.loads((Path(__file__).parent / 'reference_stations_v1.json').read_text())
        ids = config['station_ids']
    if not 1 <= len(ids) <= 30 or len(set(ids)) != len(ids):
        raise ValueError('reference_selection_requires_1_to_30_unique_stations')
    unknown = set(ids) - set(eligible)
    if unknown:
        raise ValueError('reference_stations_unavailable:' + ','.join(sorted(unknown)))
    return tuple(eligible[k] for k in ids)


def build_identity():
    root = Path(__file__).resolve().parent.parent
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True,
                                      stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                        cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError('reference_forecast_requires_git_checkout') from error
    if dirty:
        raise ValueError('reference_forecast_requires_clean_tracked_build')
    return sha, version('astropilot')


def capture_forecast(station, *, provider=None, clock=now_utc, build=None, hours=24):
    if type(hours) is not int or not 1 <= hours <= 168:
        raise ValueError('reference_hours_1_to_168')
    if provider is None:
        from astro_score import fetch_weather
        provider = fetch_weather
    sha, code_version = build or build_identity()
    snapshot = provider(station.latitude, station.longitude)
    if snapshot is None:
        raise ValueError('reference_forecast_unavailable')
    created = utc(clock())
    retrieved = utc(snapshot.retrieved_at_utc)
    if snapshot.timezone != station.timezone:
        raise ValueError('reference_timezone_mismatch')
    points = []
    for i, stamp in enumerate(snapshot.payload['hourly']['time']):
        target = datetime.fromtimestamp(stamp, timezone.utc)
        if created < target <= created + timedelta(hours=hours):
            points.append({'at': target.isoformat(), 'values': {
                variable: snapshot.payload['hourly'][variable][i] for variable in VARIABLES}})
    value = dict(station=asdict(station), points=points,
                 transport=snapshot.trust_transport(), model='provider_default_unspecified',
                 units={v: unit for v, (_, unit, _, _) in VARIABLES.items()})
    fields = dict(station_id=station.station_id, created_at_utc=created.isoformat(),
                  forecast_retrieved_at_utc=retrieved.isoformat(),
                  snapshot_json=json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False),
                  code_sha=sha, code_version=code_version, prospective=True, schema_version=1)
    return ReferenceForecastRun(digest(fields), **fields)


class ReferenceLab:
    def __init__(self, store=None, *, max_artifacts=100000):
        if type(max_artifacts) is not int or max_artifacts < 1:
            raise ValueError("invalid_reference_artifact_limit")
        self.max_artifacts = max_artifacts
        self.store = store or FileFieldLabStore()

    def save(self, kind, key, payload, stamp, station='MeteoSwiss'):
        artifact = FieldLabArtifact.create(artifact_type=kind, source_id=station,
                       idempotency_key=key, payload=payload, created_at_utc=canonical_utc(stamp))
        existing = self.store.load(idempotency_key=key)
        if existing is not None:
            # Deduplicated content keeps its first provenance; events retain each retrieval.
            previous = json.loads(existing.payload_json)
            incoming = json.loads(json.dumps(payload, allow_nan=False))
            if kind in ('reference_observation', 'reference_acquisition'):
                incoming['asset_href'] = previous['asset_href']
            if kind == 'reference_observation':
                incoming['retrieved_at_utc'] = previous['retrieved_at_utc']
            if previous != incoming or existing.artifact_type != kind:
                raise ValueError('field_lab_immutable_conflict')
            return False
        return self.store.save(artifact)

    def save_run(self, run, *, clock=now_utc):
        # Publication deadline includes actual durable write, not just retrieval.
        existing = self.store.load(idempotency_key=run.run_id)
        seal = self.store.load(idempotency_key='seal-' + run.run_id)
        completion = self.store.load(idempotency_key='durable-' + run.run_id)
        if existing is not None and seal is not None and completion is not None:
            if (existing.artifact_type != 'reference_forecast'
                    or json.loads(existing.payload_json) != asdict(run)
                    or seal.artifact_type != 'reference_seal'
                    or json.loads(seal.payload_json) != {'run_id': run.run_id, 'snapshot_digest': run.snapshot_digest}
                    or (run.prospective and any(utc(completion.created_at_utc) >= utc(p['at'])
                        for p in json.loads(run.snapshot_json)['points']))):
                raise ValueError('field_lab_immutable_conflict')
            self.durable_seal(run)
            return False
        deadline = min(utc(p['at']) for p in json.loads(run.snapshot_json)['points'])
        if run.prospective and utc(clock()) >= deadline:
            raise ValueError('leakage_detected')
        saved = self.save('reference_forecast', run.run_id, asdict(run), run.created_at_utc, run.station_id)
        sealed = utc(clock())
        if run.prospective and sealed >= deadline:
            raise ValueError('reference_seal_deadline_missed')
        # Only runs with a durable seal are comparison candidates.
        self.save('reference_seal', 'seal-' + run.run_id,
                  {'run_id': run.run_id, 'snapshot_digest': run.snapshot_digest},
                  sealed.isoformat(), run.station_id)
        # Presence after an interrupted publication is not durability evidence.
        # Reopen, validate and fsync both existing artifacts in this attempt.
        for key in (run.run_id, 'seal-' + run.run_id):
            self.store.confirm_durable(self.store.load(idempotency_key=key))
        completed = utc(clock())
        self.save('reference_seal_completion', 'durable-' + run.run_id,
                  {'run_id': run.run_id, 'snapshot_digest': run.snapshot_digest,
                   'seal_digest': self.store.load(idempotency_key='seal-' + run.run_id).digest},
                  canonical_utc(completed), run.station_id)
        if run.prospective and completed >= deadline:
            raise ValueError('reference_seal_deadline_missed')
        return saved

    def durable_seal(self, run):
        seal = self.store.load(idempotency_key='seal-' + run.run_id)
        completion = self.store.load(idempotency_key='durable-' + run.run_id)
        if seal is None or completion is None:
            return None
        if (seal.artifact_type != 'reference_seal'
                or json.loads(seal.payload_json) != {'run_id': run.run_id, 'snapshot_digest': run.snapshot_digest}
                or completion.artifact_type != 'reference_seal_completion'
                or json.loads(completion.payload_json) != {'run_id': run.run_id,
                    'snapshot_digest': run.snapshot_digest, 'seal_digest': seal.digest}
                or seal.source_id != run.station_id or completion.source_id != run.station_id
                or utc(seal.created_at_utc) < utc(run.created_at_utc)
                or utc(completion.created_at_utc) < utc(seal.created_at_utc)):
            raise ValueError('reference_seal_identity_mismatch')
        return completion.created_at_utc

    def save_catalogue(self, payload, retrieved_at, *, event_id=None):
        stamp = canonical_utc(retrieved_at)
        catalogue_digest = digest(payload)
        event = {'catalogue_digest': catalogue_digest, 'retrieved_at_utc': stamp}
        key = event_id or 'catalog-' + digest(event)
        # Reject a conflicting event before publishing new content.
        existing = self.store.load(idempotency_key=key)
        if existing is not None and (existing.artifact_type != 'catalog_activation_event'
                or json.loads(existing.payload_json) != event):
            raise ValueError('field_lab_immutable_conflict')
        self.save('reference_catalogue', catalogue_digest, payload, stamp)
        return self.save('catalog_activation_event', key, event, stamp)

    def save_observation(self, observation):
        self.save('reference_observation', observation.measurement_digest,
                  asdict(observation), observation.retrieved_at_utc, observation.station_id)
        return self.save('reference_acquisition', observation.acquisition_id,
                         asdict(observation), observation.retrieved_at_utc, observation.station_id)

    def facts(self):
        artifacts = []
        for artifact in self.store.iter_artifacts(max_names=self.max_artifacts):
            if len(artifacts) >= self.max_artifacts:
                raise ValueError("reference_artifact_limit_exceeded")
            artifacts.append(artifact)
        runs, observations = [], []
        for artifact in artifacts:
            payload = json.loads(artifact.payload_json)
            if artifact.artifact_type == 'reference_forecast':
                run = ReferenceForecastRun(**payload)
                if artifact.idempotency_key != run.run_id:
                    raise ValueError('reference_run_identity_mismatch')
                sealed = self.durable_seal(run)
                if sealed is not None and (not run.prospective or all(
                        utc(sealed) < utc(p['at']) for p in json.loads(run.snapshot_json)['points'])):
                    runs.append(run)
            elif artifact.artifact_type == 'reference_acquisition':
                observation = ReferenceObservation(**payload)
                if observation.acquisition_id != artifact.idempotency_key:
                    raise ValueError('reference_acquisition_digest_mismatch')
                observations.append(observation)
        return tuple(runs), tuple(observations)

    def collect(self, client, *, clock=now_utc, tolerance_minutes=10):
        validate_tolerance(tolerance_minutes)
        current = utc(clock())
        runs, _ = self.facts()
        due = {}
        for run in runs:
            for point in json.loads(run.snapshot_json)['points']:
                target = utc(point['at'])
                if target + timedelta(minutes=tolerance_minutes) < current:
                    due.setdefault(run.station_id, set()).add(target)
        count = 0
        for station, targets in sorted(due.items()):
            families = {'now' if t.date() == current.date() else 'recent' for t in targets}
            if any(t.year != current.year for t in targets):
                raise ValueError('reference_cross_year_collection_not_supported')
            for family in sorted(families):
                for observation in client.observations(station, family):
                    if utc(observation.observed_at_utc) <= current and any(
                            abs(utc(observation.observed_at_utc) - t) <= timedelta(minutes=tolerance_minutes)
                            for t in targets):
                        count += self.save_observation(observation)
        return count

    def comparisons(self, *, clock=now_utc, tolerance_minutes=10, persist=False, historical=False):
        validate_tolerance(tolerance_minutes)
        current = utc(clock())
        runs, observations = self.facts()
        result = []
        for run in runs:
            if run.prospective == historical:
                continue
            for point in json.loads(run.snapshot_json)['points']:
                if utc(point['at']) + timedelta(minutes=tolerance_minutes) >= current:
                    continue
                for variable in VARIABLES:
                    comparison = compare_point(run, point, variable, observations, tolerance_minutes, durable_sealed_at_utc=self.durable_seal(run))
                    result.append(comparison)
                    if persist:
                        payload = asdict(comparison)
                        self.save('reference_comparison', digest(payload), payload, run.created_at_utc, run.station_id)
        return tuple(result)


def validate_tolerance(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 30:
        raise ValueError('reference_tolerance_0_to_30_minutes')


def compare_point(run, point, variable, observations, tolerance_minutes, *, durable_sealed_at_utc=None):
    validate_tolerance(tolerance_minutes)
    target = utc(point['at'])
    # Retain the latest retrieved official revision of each measurement, then nearest timestamp.
    revisions = {}
    for observation in observations:
        if observation.station_id == run.station_id and observation.variable == variable:
            key = observation.observed_at_utc
            rank = (utc(observation.retrieved_at_utc), observation.measurement_digest)
            if key not in revisions or rank > revisions[key][0]:
                revisions[key] = (rank, observation)
    candidates = [entry[1] for entry in revisions.values()]
    nearest = []
    if candidates:
        distance = min(abs(utc(o.observed_at_utc) - target) for o in candidates)
        nearest = [o for o in candidates if abs(utc(o.observed_at_utc) - target) == distance]
    observation = nearest[0] if len(nearest) == 1 else None
    reason = 'missing_observation' if not nearest else 'ambiguous_nearest_observation'
    offset, observed, error = None, None, None
    if observation:
        observed_at = utc(observation.observed_at_utc)
        offset = (target - observed_at).total_seconds() / 60
        observed = observation.value
        if durable_sealed_at_utc is None:
            reason = 'missing_durable_seal'
        elif (utc(durable_sealed_at_utc) >= observed_at
                or (run.prospective and utc(durable_sealed_at_utc) >= target)):
            reason = 'leakage_detected'
        elif (utc(run.forecast_retrieved_at_utc) >= observed_at
                or (run.prospective and utc(run.created_at_utc) >= observed_at)):
            reason = 'leakage_detected'
        elif abs(offset) > tolerance_minutes:
            reason = 'outside_time_tolerance'
        elif observation.quality != 'unverified' or observed is None:
            reason = observation.quality
        elif variable == 'wind_speed_10m':
            reason = 'aggregation_semantics_unverified'
        else:
            reason = 'comparable_unverified_official_qc'
            error = point['values'][variable] - observed
    return ReferenceComparison(run.run_id, run.station_id, variable, point['at'],
        observation.observed_at_utc if observation else None, offset, point['values'][variable] if error is not None else None,
        observed if error is not None else None, error, abs(error) if error is not None else None,
        'comparable' if error is not None else 'non_comparable', reason,
        run.snapshot_digest, observation.measurement_digest if observation else None,
        tolerance_minutes, cohort='prospective' if run.prospective else 'historical_backfill')


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def report(comparisons, runs):
    runs = tuple(runs)
    lookup = {r.run_id: json.loads(r.snapshot_json) for r in runs}
    groups = {}
    for comparison in comparisons:
        if type(comparison) is not ReferenceComparison:
            raise ValueError("reference_comparison_required")
        comparison = ReferenceComparison(**asdict(comparison))
        run = next((r for r in runs if r.run_id == comparison.forecast_run_id), None)
        if run is None:
            raise ValueError("reference_comparison_unknown_run")
        if comparison.station_id != run.station_id or comparison.forecast_digest != run.snapshot_digest or comparison.cohort != ("prospective" if run.prospective else "historical_backfill"):
            raise ValueError("reference_comparison_provenance_mismatch")
        points = lookup[comparison.forecast_run_id]['points']
        matched = next((p for p in points if p['at'] == comparison.forecast_point_at_utc), None)
        if matched is None or (comparison.status == 'comparable' and comparison.forecast_value != matched['values'][comparison.variable]):
            raise ValueError('reference_comparison_forecast_mismatch')
        transport = lookup[comparison.forecast_run_id]['transport']
        model = lookup[comparison.forecast_run_id]['model']
        provider = transport['provider']
        for station in ('ALL', comparison.station_id):
            groups.setdefault((station, comparison.variable, provider, model, comparison.cohort), []).append(comparison)
    rows = []
    for (station, variable, provider, model, cohort), items in sorted(groups.items()):
        comparable = [c for c in items if c.status == 'comparable']
        errors = [c.absolute_error for c in comparable]
        periods = [c.forecast_point_at_utc for c in items]
        reasons = {reason: sum(c.reason == reason for c in items) for reason in sorted({c.reason for c in items})}
        rows.append(dict(station=station, altitude_m=None if station == 'ALL' else
                         lookup[items[0].forecast_run_id]['station']['altitude_m'],
            variable=variable, unit=VARIABLES[variable][1], n_comparable=len(errors),
            n_non_comparable=len(items)-len(errors),
            n_missing=sum(c.reason in ('missing', 'missing_observation') for c in items),
            mean_bias=statistics.mean(c.signed_error for c in comparable) if errors else None,
            mae=statistics.mean(errors) if errors else None,
            median_abs_error=statistics.median(errors) if errors else None,
            p50_abs_error=percentile(errors, .5), p90_abs_error=percentile(errors, .9),
            period_min=min(periods), period_max=max(periods), provider=provider, model=model,
            source='MeteoSwiss', cohort=cohort, reasons=reasons,
            policy=items[0].policy, tolerance_minutes=items[0].tolerance_minutes))
    return rows
