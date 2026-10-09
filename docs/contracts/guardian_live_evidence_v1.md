# Guardian Live Evidence Adapter v1

Explicit opt-in provider `open_meteo_current_v1`. Acquisition only; GuardianService
owns freshness/risk. No Tonight, Opportunity Alerts, Field Lab/NAS, workers,
notification or hardware. Existing astro_score.fetch_weather uses the same
https://api.open-meteo.com/v1/forecast endpoint, but its hourly seven-day ingress
omits gusts/dew point and imports unrelated planning. Reuse the endpoint, not that
client/model. Reference: https://open-meteo.com/en/docs (consulted 2026-10-09).

Current conditions are model-derived 15-minute values, provenance FORECAST,
not station observations. Evidence timestamp is current.time (Unix UTC), never
retrieval time or scheduler slot. Source identifies adapter v1, requested site,
variable and interval. API does not expose a model-run timestamp/version here;
current.time is validity time, not proof of recent model issuance. Guardian's
existing freshness checks operate on that validity time.

Mapping: positive modeled rain OR showers => rain_active true; both explicit
zero => false; otherwise missing. These are precipitation amounts for the
provider current interval, not probabilities. This describes modeled rain for that interval, not an
instant sensor reading. Probability/precipitation totals are never substituted.
No rain ETA is supplied or inferred, including no explicit “no upcoming rain”.
wind_speed_10m => wind_kmh; wind_gusts_10m => gust_kmh;
relative_humidity_2m => humidity_percent; temperature_2m - dew_point_2m =>
dew_spread_c, only with both finite explicit Celsius inputs. No humidity-derived
physical formula. Matching current_units are required for each channel. Missing
or invalid channels remain None; invalid envelope/time/interval fails acquisition.
Numeric bounds: rain 0..1000 mm, wind/gust 0..500 km/h, humidity 0..100%,
temperature/dew point -100..70 C. Negative dew spread is preserved as critical.

One synchronous HTTPS request per call, no redirects/proxies/retries/cache.
Transport uses a total deadline (default 10s, explicit 0<timeout<=30s), a bounded
64 KiB body, and no workers. POSIX foreground SIGALRM deadline covers DNS/connection/headers/body;
previous handler is restored and existing alarms are never replaced. Unsupported
platforms (including Windows), non-main threads or occupied alarm fail closed; overruns and errors
raise sanitized GuardianAcquisitionError. Missing channels yield partial
observations; periodic runner turns acquisition failures into ERROR. Missing ETA
means this provider alone cannot yield SAFE under the current complete-evidence
policy. Session source is deliberately unknown (None), never inferred from weather.

Host JSON may specify `weather_site`: exactly latitude, longitude, timeout_seconds.
Required when this built-in provider is selected and enabled. No default location.
Default disabled host performs no acquisition; injected registries replace the
built-in registry. Unknown IDs fail provider_unavailable. No UI/API additions.

V1 limit: modeled conditions, no imminent-rain evidence and no live session
provider; not sufficient for autonomous safety decisions. Next step: explicit rain
ETA and session evidence contracts before OS supervision or Guardian notifications.

Example opt-in configuration (no configuration file is installed by this PR):
```json
{"schema_version":1,"interval_seconds":60,"anchor":"2026-10-09T00:00:00+00:00",
 "enabled":true,"provider":"open_meteo_current_v1",
 "weather_site":{"latitude":46.0,"longitude":7.0,"timeout_seconds":10}}
```
