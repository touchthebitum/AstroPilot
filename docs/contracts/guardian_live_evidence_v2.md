# Guardian Live Evidence v2

Baseline: #352, main/origin/main 8bececd80c1684111bddcf18eead982b9ce50fc1.
Provider ID and opt-in host schema remain open_meteo_current_v1. V1 mapping,
units, bounds, source validity timestamps and GuardianService authority remain
unchanged. No risk thresholds, session inference, UI, notifications, OS startup,
hardware, Tonight, Opportunity Alerts, Field Lab or NAS changes.

## Portable bounded transport

Audit: requests is installed, httpx2 is test-only, and v1 uses http.client plus
POSIX SIGALRM. Socket/connect/read timeouts alone do not bound DNS or a trickle
of response headers. Requests does not provide a whole-operation wall deadline.
Use standard-library HTTPSConnection inside one synchronous ephemeral Python
child, supervised with subprocess.run(timeout=remaining). This is a foreground
acquisition boundary, not a persistent/background worker. Timeout kills and
waits for the child before returning; no threads/tasks/processes survive a call.
No shell, no executable lookup, no retries and no dependency additions.

BoundedHttpTransport accepts only validated site coordinates and 0<timeout<=30s.
It owns a fixed HTTPS api.open-meteo.com:443 /v1/forecast endpoint, certificate
verification, current-only parameters, no redirect handling, no proxy environment
lookup and no cache. Connect/socket read use the remaining budget, with a parent
wall deadline covering child startup, DNS, TLS, request, headers, body and decoding.
Only status 200 is accepted. Body is capped at 65536 bytes (including a one-byte
oversize probe). JSON constants NaN/Infinity and malformed JSON fail acquisition.
A child failure/timeout emits only acquisition_failed at the provider boundary.
Exactly one GET is attempted, at most one when failure occurs before sending.

Portability uses sys.executable and an absolute adjacent .py helper with -I:
macOS/Linux/Windows CPython 3.11-3.13, independent of SIGALRM/main-thread status.
Frozen executables fail closed: sys.executable is not a Python interpreter there.
They need a dedicated packaged child entrypoint before operational deployment.
OS process creation and kill/reap scheduling cannot have a hard real-time bound;
as documented by Python, process creation itself may not be interruptible. The
budget includes startup elapsed time and rejects late successful output. No
claim of a hard OS-level execution-time guarantee or frozen Windows support.
Reference: https://docs.python.org/3/library/subprocess.html#subprocess.run

## Explicit rain ETA decision

Source audited 2026-10-09: https://open-meteo.com/en/docs, Hourly Parameter
Definition and 15-Minutely Parameter Definition. Rain/showers are sums over the
preceding hour or preceding 15 minutes. Outside supported regions, 15-minute
values can be interpolated from hourly data. These are accumulated intervals,
not onset timestamps. The first positive interval endpoint minus current.time
would misrepresent the onset, including at Guardian's 15-minute threshold.
The current envelope also supplies validity time, not model issuance time.

No exact rain ETA is supported in v2. rain_eta_minutes stays None even with
injected hourly/minutely/probability payloads, zero samples or positive samples.
The reserved rain_forecast_window contract is absent/missing: no model field is
added without a usable consumer and validated interval semantics. No additional
forecast is requested, no zero/Infinity/no-rain default and no inferred SAFE.
Current rain semantics from v1 and stale timestamp preservation remain exact.

Future ETA needs explicit onset/uncertainty and source/reference timestamps,
verified native temporal resolution, a bounded horizon and a GuardianService
interval policy before mapping. Next gate is that evidence contract plus live
session evidence; OS supervision/autostart or notification remains opt-in future
work with no hardware automation.
