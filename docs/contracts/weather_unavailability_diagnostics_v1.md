# Weather unavailability diagnostics v1

`astro_score.fetch_weather` retains the existing timeout (15 seconds), single request,
None-on-transport-failure behavior and weather ingress validation. No retry, fallback
cache, freshness rule, productive threshold or mission authorization is changed.

It emits `weather_fetch_failed` / `weather_fetch_succeeded` records through
`astropilot.launcher.weather`, a child of the existing desktop launcher logger.
The launcher persists these records in its existing rotating `AstroPilot.log`.
Direct CLI/API hosts can route the same standard Python logger with their logging
configuration; this module does not create a new data directory or file handler.

Each message is `weather_diagnostic ` followed by one JSON object:
`schema_version`, `event`, `diagnostic_id`, `occurred_at_utc`, `provider`, `category`,
`duration_ms`, `http_status`. HTTP status is a bounded integer or null. Categories
include read/connect/generic timeout, connection/TLS/HTTP/request/unexpected error,
non-JSON response, invalid ingress payload, and validated success. A connection
failure does not establish DNS as its cause. Exception messages, traceback, URLs,
query strings, coordinates, credentials and forecast bodies are not logged.

For `/v1/tonight`, a generated `X-Weather-Diagnostic-ID` response header correlates
provider transport and API weather records. Weather 503 response bodies and codes
remain unchanged. Valid ingress/freshness failures still refuse, never authorize.
`tonight_weather_available` means weather was obtained and passed freshness checks;
it does not attest productive conditions or mission acceptance. The context is
request-local, resets on errors and supports concurrent/nested callers. Standalone
fetch calls receive independent IDs. Provider diagnostics do not depend on printing
to a frozen Windows console, so existing support-log exports retain the cause.

Scope: transport acquisition and its weather boundary. No schema/version changes
to stored decision evidence, user profiles, filter inventory, Field Lab or NAS.
A historical failure cannot be diagnosed retroactively without its original cause.
Tests inject failures deterministically, exercise real weather payload validation,
verify persistent logging in an isolated path, 503 correlation and recovery, and
ensure arbitrary exception strings/coordinates do not leak into the record.
