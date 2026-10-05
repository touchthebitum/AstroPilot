# Reference Weather Station Field Lab v1 — prospective MeteoSwiss validation

The prerequisite isolation shipped in PR #313, merged at
`77040e8536dab67268ee5487f41a91932eef978d`. This extension adds an internal,
prospective reference pipeline using that boundary. It does not recalibrate the
engine, change scores/ranking/provider reliability, or write user data.

## Filesystem boundary

`FileFieldLabStore()` is the dedicated API. It accepts no arbitrary directory
argument and has no fallback to any user store. Set `FIELD_LAB_DATA_DIR` to an
explicit absolute root. Missing configuration, relative paths and any `..`
component are rejected before storage creation. The resolved root must be
strictly disjoint from both the effective `ASTROPILOT_DATA_DIR` root and the
platform's default user root: equality and ancestry in either direction are
rejected. In particular, `<ASTROPILOT_DATA_DIR>/field_lab/` is **not allowed**.
A separate sibling root is suitable.

Paths are expanded and canonicalized (including symlink aliases) before overlap
checks. Existing endpoints and ancestors are compared by filesystem device/inode
identity, including the longest existing prefix of a destination to create.
This detects macOS case-insensitive aliases without relying on POSIX normcase.
Missing suffixes are compared conservatively with case folding from the deepest
shared real ancestor: potentially overlapping future case aliases are refused,
including on sensitive filesystems. Distinct existing directories remain distinct.
Identity lookup errors fail closed. Each operation rechecks configuration and both user roots. After resolving
the configured root, every directory component and the fixed `artifacts/`
subdirectory is opened relative to a pinned descriptor with `O_NOFOLLOW`.
Subdirectory/document symlinks and non-regular documents are refused. Replacing a path component with a symlink cannot redirect fd-relative publication.
This is not a guarantee against renaming an already opened directory.
An existing unmarked root must be empty before initialization: the API will not
claim a directory already containing arbitrary user documents. The root owns an immutable `.field_lab_namespace` marker with namespace and
schema version; readers reject a missing or incompatible marker on an existing
root. Unsupported secure filesystem capabilities, including Windows, fail
closed before any filesystem mutation. This deliberately follows Outcome
History's POSIX capability policy; Windows support needs a separately reviewed
secure backend, not a less secure fallback.

User observation, evaluation, forecast evidence, execution and lineage stores
check their directory on each access. They refuse overlap with the configured
lab root and refuse directories with a lab marker in their ancestry, including
resolved aliases. Outcome History checks both its root and each inspected
subdirectory; Recent Decisions uses that same boundary. Configuration and
namespace markers are application boundaries, not an OS permission system:
operators must preserve markers and use these APIs rather than manually
rewriting storage domains. Arbitrary custom user store locations outside the
normal effective/default roots must also be kept disjoint from the lab.

## Local-process threat model: opened-directory rename

The supported boundary protects against configuration mistakes, path traversal,
case aliases and symlink redirection. It assumes no concurrent local process
with rights to rename directories in both the lab and user domains, and no
privileged process modifying these domains. Such processes are outside the
isolation guarantee: moving an opened `lab/artifacts` to
`user/field_observations` immediately before publication still allows the fd-relative
write there. User decoders continue to exclude the lab envelope.

The writer creates directories with mode 0700 and temporary files with mode 0600;
these modes are privacy defaults, not an enforced ownership/permission boundary.
Existing parents are neither recursively chmodded nor certified as a security
boundary. Checking owner/device/inode, retaining ancestor fds or revalidating
parentage before a write cannot eliminate a subsequent rename race. On this
same-user macOS/POSIX deployment, 0700 cannot remove the owner's rename rights.
A stronger guarantee would require a separately administered writer identity
and domain permissions, or a reviewed platform-specific backend. No such boundary
is implemented or claimed here. The deterministic rename regression intentionally
records successful relocation/publication and subsequent decoder exclusion; it
must not be interpreted as a race-prevention test.

## Artifact and provenance boundary

`FieldLabArtifact` is a separate frozen model, not a user `FieldObservation`.
Every artifact carries `artifact_type`, `schema_version=1`,
`namespace=provenance=field_lab_reference_station`, `created_at_utc` (UTC only),
`source_id`, `idempotency_key`, JSON object payload and its SHA-256 digest.
Payloads are copied into immutable canonical JSON. The model and decoder reject
any other namespace/provenance/version, duplicate JSON fields and any
`calibration_eligible` value other than the boolean `false`. User models and
existing user calibration eligibility semantics remain unchanged. Lab objects
cannot enter the typed user store writer APIs.

Publication uses a flushed and fsynced temporary followed by an atomic,
create-only hard link and directory fsync. Final artifacts are immutable. The
validated idempotency key determines a SHA-256 filename: an identical rerun
returns `False`; reuse with a different envelope raises a conflict. The caller
must reuse the original UTC creation time for a rerun. Reads check envelope,
identity and payload digest; they never acquire a writer lock or create files.
There is no collection/network activity in either operation.

## Defense in depth for user readers

All six user persistence decoders explicitly reject lab namespace/provenance
markers, including nested observation `source_type`. Outcome History skips such
files with `field_lab_document_excluded` diagnostics before joining them into
observations/evaluations. Recent Decisions rejects them through its evidence
decoder. Malformed/incompatible documents continue to follow the existing
reader diagnostics. Accidentally copied lab files therefore cannot contribute
to user history rows, recent decisions or statistics, even in a user directory.
Additive lab observations/evaluations retain `field_lab_document_excluded`
diagnostics without making the snapshot incomplete; HTTP 200 and statistics of
valid user evidence are preserved. Missing observations referenced by evaluations,
and excluded required forecast/execution/decision joins, remain blocking with
`missing_user_observation` or `expected_user_document_excluded` diagnostics.
An excluded file at a 64-hex user evaluation identity is conservatively treated
as a lost/ambiguous user proof unless its name is the lab idempotency-key hash.
Thus arbitrary additional lab files with user-shaped evaluation identities can
still suspend statistics; there is no trusted historical manifest to distinguish
all additions from replacements. Likewise an unreferenced removed evaluation
cannot in general be reconstructed from surviving files. The contract does not
claim to detect every past deletion or deliberate replacement with a lab hash.
Diagnostics/fingerprints may reflect extra files; valid user data is unchanged.

## Prerequisites for the next lot

Offline tests cover disjoint roots, both overlap directions, default-root
protection, symlink aliases and redirection, traversal, missing configuration,
capability failures, immutable/idempotent publication, digest validation,
calibration exclusion, all user decoders and user history/statistics preservation.
Review this lot read-only and merge it before any station integration. Subsequent
station code must construct only the dedicated lab model/store and preserve this
boundary; it must not reuse user application factories or publish lab artifacts
into user sessions, profiles or histories.


## Prospective protocol and dedicated models

`ReferenceStation`, `ReferenceForecastRun`, `ReferenceObservation` and
`ReferenceComparison` are dedicated frozen v1 dataclasses in
`astropilot/reference_station_lab.py`. Every persisted document is wrapped in
`FieldLabArtifact`: namespace/provenance `field_lab_reference_station`,
`calibration_eligible=false`, immutable canonical payload SHA-256 and v1 schema.
No user project, observation, session, mission, profile or decision is fabricated.

1. Synchronize official metadata and persist a catalogue plus active selection.
2. Call **the production `astro_score.fetch_weather` chain**, with exact station
   coordinates. Production resolves the timezone and validates provider units,
   cadence, values and grid distance. The provider is Open-Meteo **for forecasts
   only**; observations are exclusively MeteoSwiss.
3. Keep future points within 24 hours (configurable 1–168), temperature, humidity
   and wind, requested/grid coordinates, provider retrieval time, grid altitude,
   station metadata, code SHA/version and snapshot digest. The provider does not
   expose its resolved model: record `provider_default_unspecified`, never infer
   a model. Require a clean tracked Git checkout build (forecast capture from a standalone
   installed wheel without its Git checkout is unsupported). A fresh provider call creates a new
   run, never reconstructs an old run.
4. Persist the forecast and then an immutable seal. Both retrieval and creation
   must precede every target. Check the clock before and after the durable
   forecast and seal publication, then publish a fresh completion candidate and its commit. A missed deadline leaves an
   inadmissible artifact, which readers exclude. The attested forecast durable seal time must also precede every
   target. Identical successfully committed runs are no-ops, including after the deadline.
5. After target + tolerance has passed, collect official measurements, select the
   unique nearest observation and compare stored facts only. Any observation at
   or before retrieval/creation/durable seal completion produces `leakage_detected`, even when nearby.

Local wall clocks must be correct. Digests protect against accidental changes,
not a hostile owner forging artifacts or changing the clock. The accepted P3
opened-directory rename limitation above continues to apply to every operation.

## Official source contract and attribution

Source: **MeteoSwiss**. Documentation inspected 2026-10-05:

- https://opendatadocs.meteoswiss.ch/a-data-groundbased/a1-automatic-weather-stations
- https://opendatadocs.meteoswiss.ch/general/download
- Collection: `ch.meteoschweiz.ogd-smn`
- STAC: `https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn`
- Metadata under `https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/`:
  `ogd-smn_meta_stations.csv`, `ogd-smn_meta_parameters.csv`,
  `ogd-smn_meta_datainventory.csv`.
- Per-station items `/items/{lowercase-three-letter-id}`, assets
  `ogd-smn_{id}_t_now.csv` (today) and `_t_recent.csv` (current year to yesterday).

Reuse the existing read-only STAC downloader: official HTTPS host, no redirects,
fixed timeouts, bounded asset download and mandatory STAC SHA-256 checksum.
CSV is CP1252, semicolon-separated; `reference_timestamp` has format
`DD.MM.YYYY HH:MM`, explicitly interpreted in UTC as documented. Metadata supplies
name, coordinates, altitude and station identifiers; active variables come from
inventory entries without `data_till`. The parameter catalogue must confirm exact
units and `T` granularity before a catalogue is accepted. Persist a combined
metadata digest and the complete station catalogue, with explicit active IDs.

| Provider variable | Official parameter | Unit | v1 comparison |
| --- | --- | --- | --- |
| temperature_2m | tre200s0 | °C | instantaneous air temperature at 2 m |
| relative_humidity_2m | ure200s0 | % | instantaneous relative humidity at 2 m |
| wind_speed_10m | fu3010z0 | km/h | captured; non-comparable aggregation semantics |

`fkl010z0` is the official mean scalar wind in m/s, but is not substituted for the
km/h parameter. The forecast provider does not establish matching ten-minute
aggregation semantics, so wind contributes no numerical error statistics.
Precipitation and pressure are deferred. No cloud cover, seeing, transparency or
OIII quality is inferred from station data.

The current CSV supplies no per-measurement validated QC flag. Finite,
range-checked temperature/humidity values are comparable under the **explicit
unverified official QC cohort policy**, reason
`comparable_unverified_official_qc`; they are not claimed to be validated.
Empty cells and absent variable columns become missing, malformed/non-finite/
out-of-range values become invalid, never zero. Any nonempty supplied `_qc` field
is conservatively rejected until its official semantics are implemented.
Official revisions are immutable observation versions keyed by measurement
content; separate acquisition events retain each retrieval. The latest event
timestamp wins; divergent content at that timestamp fails closed. Exact event replays are no-ops.

## Station selection and volume

`astropilot/reference_stations_v1.json` is the packaged, versioned default:
NEU, CDF, CHA, PAY, BER, BAS, GVE, SIO, LUG, DAV, JUN, SAE (12 stations).
NEU/CDF/CHA cover Neuchâtel/Jura; the remaining sites cover lowlands, western,
central, southern and alpine Switzerland, including high altitude JUN/SAE.
Selection requires active temperature + humidity + mean wind inventory entries.
Unavailable IDs fail explicitly rather than silently changing the cohort.
`--stations NEU,CDF` overrides selection; `--all` explicitly opts into all eligible
sites. Ordinary selection is capped at 30. No full-Switzerland smoke or scheduler
is run. Catalogue snapshots preserve the actual selection used. Each forecast
also embeds its station metadata.

## Matching and descriptive reports

Policy `nearest-unique-no-interpolation-v1`, default tolerance **10 minutes**,
configurable 0–30. This is a dedicated Field Lab policy because the existing user
comparison uses user evidence models and validated QC; its nearest-neighbor and
ambiguous-tie refusal are preserved here. Select per station/variable, deduplicate
measurement revisions first, reject equal nearest timestamps, store exact offset
**forecast timestamp minus observation timestamp**, and refuse out-of-tolerance
pairs. No interpolation or hourly aggregation occurs. Collection keeps only
past observations within tolerance of due stored targets. Before the full
matching window closes, a target is pending and omitted from report N.

Reports group by station/variable/provider/model/cohort, plus station `ALL` for
variable-level global aggregates. They provide N comparable/non-comparable/
missing, signed forecast-minus-observed bias, MAE, median, linearly interpolated
p50/p90 absolute error, target period bounds, source, altitude, policy, tolerance
and reason counts. Empty statistics are JSON null. N counts run/target/variable
pairs; overlapping forecast runs remain distinct leads and are not independent
samples. Reports recompute from sealed snapshots and current immutable observation
versions, so old missing comparison artifacts cannot double-count a later match.
Persisted comparison artifacts remain audit evidence rather than an additive
statistics table. Re-run reports with the same tolerance for comparable cohorts.

Backfill models can be marked `prospective=false`; default readers/reporting exclude
these. `report --historical` selects only `historical_backfill`, never mixes it into
prospective totals. There is no historical forecast reconstruction command.
Cross-year observation collection is explicitly unsupported in v1; historical
asset discovery must be added before evaluating previous-year targets.

## Commands and export

Use a separate **empty** root, never under the user root:

```sh
export FIELD_LAB_DATA_DIR=/absolute/separate/nightmerit-field-lab
uv run astropilot-field-lab stations sync
uv run astropilot-field-lab stations list
uv run astropilot-field-lab forecast-run --stations NEU,CDF --dry-run
uv run astropilot-field-lab forecast-run --stations NEU,CDF --hours 24
# Later, after targets + tolerance have elapsed:
uv run astropilot-field-lab observations collect
uv run astropilot-field-lab compare --tolerance-minutes 10
uv run astropilot-field-lab report --export
uv run astropilot-field-lab report --historical
uv run astropilot-field-lab cycle --dry-run
uv run astropilot-field-lab cycle
```

All output is console JSON, directly exportable using shell redirection. `--export`
saves an immutable report artifact **inside the isolated store**, with the same
provenance as other artifacts. The CLI offers no arbitrary output path. `cycle`
collects due observations, compares and prints the report; capture new forecasts
explicitly with `forecast-run`. `cycle --dry-run` performs no network call and no
write, including when the configured root does not yet exist. No cron, launchd
or GitHub Actions are introduced.

Storage keeps #313's descriptor-pinned hashed filenames under `artifacts/`.
Logical partitions are one catalogue version, one forecast per run/station,
one seal and attestation commit per run, with completion candidates per attempt, one observation per station/timestamp/variable/revision and
one acquisition event per retrieval/content and
one comparison per run/target/variable/observation/policy. No monolithic history
JSON or mutable index is introduced. The reader checks namespace, digest and
filename identity; unknown filenames, malformed envelopes and symlinks fail
closed. Identical scientific facts are no-ops, changed content with an existing
key conflicts. Enumeration currently scans all artifacts; physical directory
sharding and retention are deferred, and should be separately reviewed before
long-term large-volume operation.

## Scientific limitations and validation

Stations represent local meteorological measurements, not complete astronomical
truth. Provider grid altitude/terrain differs from station exposure. Indirect
assimilation of past station measurements by forecast models is possible; the
strict timestamp protocol prevents direct future-observation leakage but does
not claim statistical independence from the forecasting system. This is
**descriptive weather validation**, with no automatic calibration, reliability
update, adjusted forecast or score/ranking change.

Tests under `tests/field_lab/` use minimal official-shaped catalogue/parameter/
inventory fixtures, missing/QC/invalid-value 10-minute rows and injected provider
snapshots. Network tests are never required by CI. They cover model identity,
metadata units, timestamps, sealing/deadlines, leakage, unique nearest matching,
missing observations, wind exclusion, statistics, idempotence, immutable reader
validation, user storage preservation, CLI dry-run and inherited capability/
namespace protections. A real smoke is limited to one or two explicitly selected
stations and an isolated temporary root; no expired fake forecast is published.

## Validation of this implementation (2026-10-05)

- Offline Field Lab + packaging contracts: 115 passed, 1 filesystem-specific skip.
- Full suite with bundled Node and local-listener capability: 4,901 passed,
  1 filesystem-specific skip (44 existing astronomy warnings).
- Locked dependency resolution and wheel build succeeded. The wheel includes the
  explicit CLI entry point and versioned selection config; beta version unchanged.
- Controlled real smoke at 10:41 UTC, NEU/CDF only: catalogue 159 stations;
  each station's official NOW CSV passed STAC checksum verification and yielded
  189 parsed variable values (63 ten-minute rows, three variables). Latest official
  timestamp: 10:20 UTC. Read-only parser inspection did not persist these past values.
- Production forecast capture stored two genuinely prospective 24-point snapshots
  plus the original seals in a fresh temporary Field Lab (five artifacts
  including catalogue). Every artifact is calibration-ineligible. No user root
  was created. Dry-run cycle made zero network calls and zero writes.
- This smoke predates the final candidate/commit completion protocol and catalogue activation events; it did
  not test either mechanism. No new network smoke has been performed since. A new
  controlled smoke is required after validation of the corrected HEAD and before
  real automated collection.
- The real prospective report is empty until targets mature; no real MAE/bias is
  claimed from the smoke. End-to-end comparison/statistics are verified offline.
- No push, PR or scheduler was created. Physical sharding, cross-year observation
  asset discovery, explicit validated QC and compatible mean-wind aggregation
  remain deferred. The accepted local P3 rename limitation is unchanged.


### Review corrections: durable sealing and acquisition history

Publication uses create-only forecast snapshot, seal, completion candidate and
commit artifacts. Snapshot and seal are revalidated and fsynced before the candidate.
Each attempt uses a fresh candidate identity; its publication must return successfully
from file and directory fsync (including cleanup) before the forecast durable seal timestamp is
sampled. The commit binds the candidate's complete canonical document digest, run,
snapshot and seal. Readers require and validate this commit and all its bindings;
a visible candidate alone, including a legacy receipt, never admits a run.
The timestamp attests the candidate and snapshot/seal durability already confirmed
in that attempt. Commit publication errors withdraw the newly linked commit in the
running process, leaving the candidate orphaned and inadmissible. A crash before
commit publication also leaves an orphan. A visible commit attests a successfully
confirmed candidate; visibility of the candidate cannot produce that attestation.
These are application/fsync guarantees, not a simulation of physical power loss
or protection against same-owner tampering. A fresh real smoke remains required.

Recovery validates orphan identities/content and reconfirms snapshot/seal, creates
a fresh candidate and samples a new forecast durable seal time; it never promotes an old timestamp.
A recovery after the target records a late commit, reports
`reference_seal_deadline_missed`, and remains inadmissible. Conflicting orphan
content fails closed. Successful durable replay is immutable and idempotent.
The completion instant must be strictly before the matched observation and every
prospective target. This relies on a trusted local clock.

Each official acquisition now has a distinct immutable `reference_acquisition`
artifact, identified by canonical observation content and retrieval provenance.
Content artifacts remain deduplicated by measurement digest. Matching uses the
latest acquisition timestamp, so A(T1), B(T2), A(T3) selects A(T3). An exact
replayed event is a no-op; conflicting content under the same event ID is refused.
No absent official revision identifier is assumed. Existing legacy content-only
observations are not promoted into acquisition events; recollect explicitly.

All reference domain timestamps are canonical UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`
before IDs, digests, matching or reports. Zero-offset `+00:00` inputs are equivalent;
nonzero offsets, including local DST timestamps, remain rejected. Snapshot point
order must be strictly increasing and unique. Old noncanonical run identities
are not silently migrated or rehashed: they fail closed and require a fresh
prospective capture, never a reconstructed forecast.

`ReferenceComparison` validates schema, provenance, cohort, identities, variables,
UTC instants, finite offsets, tolerance, status/reason consistency, physical bounds
and arithmetic (absolute tolerance 1e-9, relative 1e-12). Noncomparable numerical
values are null. Units are determined by the variable contract. Reports revalidate
instances at their boundary, including instances mutated through low-level access.
The existing separate `historical_backfill` cohort name is retained.

Identical station metadata/selection syncs reuse the catalogue artifact, excluding
acquisition time from its logical payload. Forecast hours are validated before
storage access, equally in dry-run and execution. `facts()` fails closed above
`ReferenceLab(max_artifacts=100000)`; it still scans the store linearly and retains
up to that many artifacts. This is a bounded materialization, not an indexed store.
Temperature and RH alone yield numerical errors. Wind aggregation and official QC
remain unverified; no calibration, scoring, ranking or provider reliability changes.


### Interrupted seal publication and catalogue activation

Every recovery reopens snapshot and seal without following symlinks, validates
regular files, bounds, envelopes and digests, and fsyncs their descriptors and
pinned parent before publishing a fresh candidate. An incomplete attempt is never
certified by its original time. Missing commits exclude runs from `facts()`;
invalid commits fail closed. No user stores are read or migrated.

Catalogue metadata/selection content is deduplicated by payload digest. Each sync
also records a distinct `catalog_activation_event`, binding that digest and canonical
sync timestamp. Same timestamp and content replay is a no-op; same content at a
new timestamp creates an activation only. Active selection uses the greatest event
timestamp, independent of ingestion order; all events at the maximum timestamp must agree on the content digest. Equal-time
identical content is accepted; divergent content raises
`reference_catalogue_activation_ambiguous`, including in CLI consumers. Filesystem
and ingestion order cannot select a winner. No official revision order is invented.
Conflicting content under an explicit event ID fails closed. Activations do not
enter observations, comparison counts or statistics. Legacy catalogues without
activation events require an explicit sync; there is no inferred activation.

`iter_artifacts(max_names=100000)` bounds all directory entries, including temporary
names, before sorting or reading artifact payloads; exceeding it raises
`field_lab_name_limit_exceeded` without a partial result. `facts()` and catalogue
selection pass `ReferenceLab.max_artifacts` as this bound. Payload materialization
remains linear and can retain up to the configured count of 16 MiB documents;
this is not an indexed or streaming statistics store.

An `unverified` observation requires a finite real value at model construction.
Missing parser values are explicitly `missing` with null value from ingestion
through matching; missing is never zero. Official QC remains unverified for real
values until an official QC contract is available. Temperature/RH mapping, excluded
wind errors, prospective/historical separation and isolation #313 are unchanged.

### Scientific temporal contract (Field Lab v1)

The scientific boundary is the successful durable confirmation of the forecast
snapshot, seal and fresh candidate. The commit envelope's `created_at_utc` stores
`forecast_durable_at_utc`: a clock sample after that barrier, before commit creation.
It does not measure completion of the commit's own fsync. The candidate envelope's
time is sampled before candidate publication and is not the admission timestamp.
The persisted format is unchanged.

Exact writer order: snapshot/seal publication, snapshot file+directory reconfirmation,
seal file+directory reconfirmation, candidate temporary write/flush/file fsync,
candidate hard link, directory fsync, temporary unlink, cleanup directory fsync,
forecast durable time sample, commit temporary write/flush/file fsync, commit hard
link, temporary unlink, commit directory fsync. No commit is constructed if the
candidate publication or reconfirmation fails. Readers validate run/snapshot/seal
and the complete candidate document bound by the commit. Admission requires this
attested time strictly before every prospective target; comparison also requires
it strictly before the matched observation.

A reader may admit a visible commit before its directory fsync, including a commit
surviving process interruption there: its existence causally follows the earlier
successful forecast barrier. Delayed commit persistence across target does not
change the earlier scientific event. If the commit disappears, the run is absent
(an acceptable false negative). Handled publication failures still roll back the
commit; orphan recovery reconfirms and samples a fresh time, never backdates it.
No third marker is required.

An artifact containing a timestamp sampled after its own final fsync requires
another write to store that sample, and that write requires another fsync. Repeating
this cannot close the self-attestation regression. A transactional database can
provide a different externally defined commit boundary, but its stored timestamp
is still not inherently a post-fsync sample.

Option A retains the current causal protocol with minimal complexity and satisfies
local Field Lab v1. Option B (SQLite with durable transactions) can simplify atomic
relationships and recovery but adds migration, connection and transaction semantics
and does not inherently provide a trusted post-commit wall-clock receipt. Option C
(an external ledger/service) can supply independently timed receipts but adds network
availability, identity, operation and trust requirements. Neither stronger option
is required to ensure the forecast content was fixed before target/observation.

This contract assumes trusted application execution, a truthful local clock and
filesystem/hardware honoring successful fsync. It does not protect against hardware
failure, a lying clock or same-owner artifact forgery. Missing evidence cannot be
reconstructed afterwards using an old timestamp. Physical power-loss behavior has
not been verified.

## Persistent bounded collection (next lot, 2026-10-05)

This section supersedes the original smoke-only cycle/scheduler/volume instructions
above. The smoke remains validation evidence and is **never automatically imported**.
No calibration, scoring or provider verdict is introduced. Temperature/RH alone
produce numerical errors; wind remains non-comparable and QC remains unverified.

### Explicit persistent root and initialization

Proposed macOS root: `~/Documents/NightMerit Field Lab/reference-weather-v1`.
This visible, stable directory is separate from
`~/Library/Application Support/AstroPilot`. The proposal passed the #313 overlap
validator on the development machine without creating it. Operators must also
check any custom user store roots outside the effective/default roots; these cannot
be discovered automatically. There is no default storage fallback:

```sh
export FIELD_LAB_DATA_DIR="$HOME/Documents/NightMerit Field Lab/reference-weather-v1"
uv run astropilot-field-lab init
uv run astropilot-field-lab status
uv run astropilot-field-lab cycle --dry-run
```

`init` uses the existing descriptor-pinned marker boundary, validates effective
and default user roots before creation, and refuses a nonempty unmarked directory.
It creates only the isolated root/marker/artifacts. It does not sync, import the
smoke, capture a forecast or enable a scheduler. Configuration/isolation errors
fail closed at every store access. This lot does not initialize the proposed root
on the user's machine.

### Cadence, bounded horizon and content/audit semantics

`cycle` refreshes catalogue/selection at most weekly, preserving configured active
IDs. The first cycle uses the packaged 12-station selection; initialize a custom
selection with `stations sync --stations NEU,CDF` before enabling. It captures a
fresh prospective 24-hour forecast only when each selected station's last sealed
run is at least 12 hours old. It never reconstructs a missed run or backfills a
historical forecast. Provider/model metadata remain the production chain's facts.
This is an initial conservative sampling policy, not an assertion that the
provider publishes a new model version every 12 hours.

Observation collection is hourly and restricted to stored prospective targets
whose complete nearest ±10-minute window is closed, with a **7-day revision
horizon**. Outside this horizon, existing scientific facts remain readable and
contribute to longitudinal reports; old missing data are not repeatedly retried.
There is no sub-minute polling. Manual `observations collect` also uses this
horizon and measurement coalescence. Cross-year asset discovery remains unsupported:
near January 1, due previous-year targets inside the horizon are reported individually
in `noncollectable_targets` as `reference_cross_year_collection_not_supported`.
Current-year targets continue collection; these unsupported targets do not block
the entire cycle.

Within a cycle, an advisory nonblocking lock serializes cycles. Concurrent attempts
fail with a nonzero error rather than racing forecast captures. A successful UTC
hour slot makes a repeat cycle in that slot a no-op (zero network calls/writes),
including after process restart. This slot is not a retry loop: failed cycles are
visible and may be explicitly retried. Partial successful forecast seals survive
and are respected on retry; they are never rebuilt with an earlier timestamp.

Scientific content (forecast, observation revision, comparison, identical report)
remains immutable and deduplicated. Acquisition history is append-only. Unchanged
measurement content **and asset href** are coalesced against the most recent
acquisition for the station/variable/timestamp. A→B→A creates three events, retaining
revision precedence; repeated A does not create another measurement acquisition.
A changed official asset produces a separate `official_asset_activation` binding
href, station/family, verified STAC checksum, downloaded SHA-256 and retrieval time.
Unchanged asset hashes are coalesced; A→B→A asset reversions retain all three
activations. The prior activation remains evidence until the next activation;
these are observed retrieval transitions, not proof of the provider's exact
publication instant. Metadata activations remain weekly acquisition evidence.
Hourly success and first-error envelopes provide bounded-frequency operational
history; error details are also emitted on stderr or to rotating scheduler logs.
Failures in checksum/network/parsing never produce synthetic observations or
zero values and return a nonzero exit code.

### Retention and capacity: explicit conservative fallback

No physical compaction or expiry is implemented in this lot. Deleting acquisition
history safely requires a versioned compaction proof understood by the existing
latest-acquisition reader; removing it would silently change revision precedence.
**All unique observations, acquisitions, forecasts, seals, comparisons, reports and
asset transition proofs are retained.** Temporal coalescence and the 7-day
collection horizon prevent redundant event spam. No unique scientific fact is
silently removed. This is the request's calculated-capacity fallback, not a claim
of infinite storage or a completed indexed/compacted long-term backend.

The **2,000,000 artifact ceiling is an enumeration safety guard, not an
operational capacity promise**. The operational soft limit is **20,000 artifacts**.
Writes stop strictly below 90% of the smaller of the configured ceiling and this
soft limit. Before a CLI mutation or cycle begins, it reserves the smaller of
15,000 artifacts and one sixth of that stop threshold: normally **3,000**.
Consequently `effective_stop_at=15,000`, `blocked=true` at 15,000, and warning
starts at 80% of the effective threshold (**12,000**). The cycle and CLI refuse
at exactly that blocked boundary, before network activity. A batch already admitted
can consume its reserve, but each publication rechecks its shared in-lock count
and cannot reach the hard write stop (**18,000**). Partial immutable facts remain
valid if a batch exhausts its budget; retry does not invent observations.

`usage` exposes `capacity`, `operational_soft_limit`, `warning`, `blocked`,
`remaining` (individual writes available below the hard stop), `reserved_budget`,
`effective_stop_at`, and `would_block_next_cycle`. The growth estimate uses the
effective entry boundary, not the 2M guard. The 10k-artifact synthetic regression
is evidence for bounded scans and decoding, not a production throughput promise
or proof of sustained operation at the soft limit. There is no advertised
160-day operating horizon. Increase capacity only after representative filesystem,
latency, disk-growth and recovery measurements, and a compaction design.

All scientific writers and the scheduler use the same `.writer.lock` in the
validated dedicated root. A process/thread reentrant boundary covers planning,
budget calculation and publication for a mutation batch; a nonblocking POSIX
`fcntl.flock` prevents other processes from entering. Contention returns the stable
`field_lab_writer_busy` error immediately. A retry must reacquire and recount,
never reuse a prior remaining budget. Lock creation is descriptor-relative,
no-follow and restricted to regular files. Init validates/publishes the namespace
before opening the writer lock; simultaneous init remains idempotent. Read-only
scans do not take this lock and can observe an interrupted batch; they never
present a multi-file transaction guarantee. The #313 same-owner directory-move
threat model remains unchanged.

### Scans, observation indexing and incremental comparisons

Artifact filenames are enumerated with constant memory (no global name list).
Lightweight `metadata/` sidecars contain type, station, variable, target/observation
bounds, revision identity, and envelope digest. They are disposable derived data;
the artifact remains authoritative. Missing sidecars after interruption or on
legacy stores fall back to a validated envelope read. Readers do not migrate a
legacy store. A normal new-store `status`/`usage` loads no scientific payloads;
legacy missing sidecars can require payload decoding. A filtered payload load
checks its envelope against its sidecar. This is not a defense against a malicious
same-owner process rewriting the derived metadata and hiding facts.

`iter_facts(...)` and `facts(..., stream=True)` support artifact type, station and
time bounds. The tuple-returning `facts()` compatibility API remains for existing
callers, while the cycle uses filtered scans. Metadata scans remain O(total files)
and incur filesystem I/O; they are not a database range index.

A comparison scan builds active observation revisions once, using canonical
(station, variable, observed timestamp) identities and the existing deterministic
retrieval-time/digest revision ordering. Sorted timelines provide nearest lookup
by binary search. Cost is O(A log A + T log A + K), with O(A+T) index/state memory,
where A is scanned acquisition metadata, T stored targets and K comparisons
requiring recalculation. At most two candidate payloads per computed variable
are loaded. Off-station/variable observations add one metadata/index pass, not
one scan per target. Nearest ties remain non-comparable, tolerance remains ±10
minutes, and there is no interpolation.

Immutable `reference_comparison_state` receipts record input acquisition identities,
computed time and the corresponding comparison. They preserve A→B→A even when
the A comparison content is deduplicated. A fully compared unchanged run is skipped
before decoding its forecast or validating its seals again. New closed targets
and targets invalidated by relevant revision identities are computed; open targets
remain untouched. `last_comparison` uses computation/receipt time, while scientific
forecast and observation timestamps remain unchanged. Legacy comparisons without
a computation receipt expose `last_comparison=null` and
`comparison_time_unavailable=true`; their scientific time is not presented as an
unknown historical execution time.

24h/7d/30d reports filter persisted comparison receipts by forecast target time
before loading payloads and load only the referenced forecasts. CLI report does
not perform a preliminary full comparison. If a window has no persisted results,
a compatibility reconstruction filters forecasts and targets at the start.
Exact medians/p90 still retain values, so all reports have a strict **20,000
comparison-envelope/receipt limit** checked from metadata before payload loading;
reconstruction also guards the candidate target upper bound. Exceeding it returns
`field_lab_report_operational_limit_exceeded_use_shorter_period`. This deliberately
uses a bounded exact aggregation instead of claiming an unlimited streaming percentile.

Secure persistent storage/locking requires POSIX descriptor capabilities and
`fcntl` (supported macOS/Linux). Imports and `--help` do not require `fcntl`.
Scheduler status can render safely on unsupported systems; other read-only
storage commands fail closed with `field_lab_secure_storage_unavailable` if secure
reads are unavailable. Mutations fail with `field_lab_secure_lock_unavailable`
or the secure-storage capability error, never an unconditional import failure.

### Year boundary

Annual asset lookup is still unsupported. On January 1 the cycle partitions
closed targets: prior-year targets are exposed in `noncollectable_targets` with
`reference_cross_year_collection_not_supported`, while current-year targets
continue normal now/recent acquisition in the original prospective cohort.
The seven-day revision horizon therefore does not stop the whole cycle for seven
days. No observations or replacement forecasts are fabricated for old targets.
The regression spans December 31 to January 1; real annual-asset collection remains
future work.

### Opt-in launchd scheduler and logs

```sh
uv run astropilot-field-lab scheduler install
uv run astropilot-field-lab scheduler status
# Only after READ-ONLY review and explicit final operator validation:
uv run astropilot-field-lab scheduler enable
uv run astropilot-field-lab scheduler disable
uv run astropilot-field-lab scheduler uninstall
```

`install` requires an existing store initialized by explicit `field-lab init`.
The runner also refuses an absent/uninitialized store (`field_lab_init_required`).
Neither implicitly initializes data. `install` only renders an immutable, disabled
`scheduler.plist` inside the lab;
it performs no launchctl command and writes no LaunchAgents file. The plan pins
the Python interpreter, checkout working directory, isolated lab root and effective
user root for overlap protection. Changing those requires uninstall/reinstall.
The checkout/interpreter must remain available and tracked-clean for production
forecast capture. `enable` is macOS-only: explicitly publishes
`~/Library/LaunchAgents/org.nightmerit.field-lab.plist` and bootstraps the GUI
launchd job, including login persistence. It validates plan/isolation/capacity,
and withdraws a newly published login plist if bootstrap fails. `disable` boots out
the job and removes its login plist; `uninstall` also removes the lab plan.
Data and logs remain after uninstall. There is no KeepAlive polling loop.

The job calls the dedicated bounded cycle runner every **3,600 seconds**;
`RunAtLoad=false`. It uses no application factory/user-store writer.
`status` performs a read-only `launchctl print` only when an installed plan exists
on macOS. Scheduler command tests inject launchctl and sandboxed login destinations;
CI never requires or activates real launchd.

Logs are `<FIELD_LAB_DATA_DIR>/collection.log` plus `.1`, `.2`, `.3`, at most
1 MiB each (4 MiB total), records capped at 64 KiB. Rotation uses pinned root
operations and no-follow regular-file checks, with private new-file modes.
The multi-rename rotation is not an atomic transaction: a crash between renames
may leave fewer backups. Each file remains size-bounded; restart resumes rotation
without a promise to preserve every log record. There are no unbounded
StandardOutPath/StandardErrorPath files. The original #313
same-owner directory-rename threat assumption still applies. Errors are never
silently treated as successful cycles. A failed isolation/capacity boundary may
prevent writing an error envelope; stderr/log still reports the failure.

### Longitudinal exports

```sh
uv run astropilot-field-lab report --period 24h
uv run astropilot-field-lab report --period 7d --format json
uv run astropilot-field-lab report --period 30d --format csv
uv run astropilot-field-lab report --period all --export
uv run astropilot-field-lab report --historical --period 30d
```

Periods filter stored forecast target timestamps relative to current UTC, never
reconstructing forecasts. Reports retain N, bias, MAE, median/p90 absolute error,
missing/non-comparable counts, actual target bounds, station altitude,
provider/model and reason counts. Prospective is the default; historical remains
a distinct explicitly selected cohort. CSV encodes reason maps as sorted JSON;
JSON/CSV columns and ordering follow the existing deterministic report schema.
`--export` saves immutable deduplicated content inside the isolated lab.

The recalculation performed by `compare` remains incremental. After that step,
`compare --export` aggregates the complete active state of persisted comparisons
for the requested scope and cohort, with the same semantics as
`report --period all`. A rerun without changes retains the existing active comparisons
and does not produce an empty export. A partial revision replaces the affected
active comparison while preserving all other active comparisons in the export.

Overlapping run/target pairs remain distinct forecast leads, not independent
samples. No causal conclusion, recalibration or automated provider verdict follows.

### Offline validation of persistent collection

On 2026-10-05, the targeted Field Lab suite passed **154 tests**, with one
case-sensitive-volume test skipped on this case-insensitive macOS volume.
The complete suite passed **4,974 tests**, with the same one skip and 44 existing
astronomy warnings, using the bundled Node runtime and permitted local listeners.
`git diff --check` and module compilation passed. Scheduler enable/disable tests
used injected launchctl and temporary login-plist destinations only. The proposed
persistent root and actual login plist were not created; no real scheduler was
installed/enabled. The critical stash and beta.7 were preserved. A real collection
smoke on this new implementation and large-volume performance validation remain
outside this offline lot and require the requested READ-ONLY review first.
