# Tonight analysis waiting and diagnostics

`POST /v1/tonight` returns a `Server-Timing` header with `total`, `weather`, and
`calculation` durations in milliseconds. Stages that were not reached are omitted.
`total` also covers validation, response preparation and serialization; it need not
equal the sum of the other stages. It does not include the browser connection or
queueing before the middleware runs.

`X-Analysis-Diagnostic-ID` correlates the fixed-schema `analysis_diagnostic` log
with existing weather events via `X-Weather-Diagnostic-ID`. Logs contain durations,
status and an opaque identifier, never request bodies, coordinates or exception
messages. Unexpected server failures are logged even when the framework emits its
own generic 500 response without our headers.

The browser displays a slow-analysis notice after 10 seconds, without claiming a
particular stage is responsible. After 90 seconds without a complete response
(including body decoding), it stops waiting and returns to availability. Inputs
are preserved, controls are restored, and no automatic retry occurs. A late
response cannot become a displayed or accepted recommendation. Aborting the
browser request does **not** promise to cancel server-side calculations; this
path does not start or credit an imaging session.

SkyEngine reuses the apparent Moon position across targets within one engine.
The bounded cache keys the complete two-part Astropy time, time scale and exact
latitude/longitude, without rounding. Vector times bypass it. No data is shared
between engines or requests. Lunar geometry and quality thresholds are unchanged.

Validation includes deterministic stalled-fetch/body/late-response UI tests,
request timing/error/privacy tests and direct uncached Astropy comparisons across
sites, targets and both sides of the daylight-saving fold. The standalone
`tests/ui/analysis_wait_browser.cjs` exercises the visible notice and timeout in a
real browser with synthetic HTTP responses and an enabled browser sandbox.
