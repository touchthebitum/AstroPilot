# Opportunity Alerts user status v1

Baseline main == origin/main == a4914461a66449e6042fa81ab8dbb20f45f70343 (#341).
Existing JSON host events expose cycle and delivery status; the UI exposes none.
This additive observer publishes a small atomic, versioned status snapshot in the
host's user data root. GET /v1/opportunity-alerts/status reads it without invoking
Tonight, claiming alerts, sending notifications, creating directories or locks.
The status dialog loads on demand and offers manual refresh, no polling.

The snapshot records startup configuration (policy enabled and notification
channel), last event time, last successful completed cycle, last delivery result
with timestamp, latest operational error and cooperative shutdown. Success means
completed scheduler operation and a non-error cycle; it does not mean an alert
was found or a notification displayed. DELIVERED means accepted by the OS only.
Missing snapshot means unknown (including an older installed host), never disabled.
Policy enabled and notification channel disabled are shown separately.
Config is last observed at startup; changing a config does not update this view
until the host restarts. No UI configuration changes or OS task control.

No claim of process liveness: recent events mean recent activity, shutdown means
last recorded cooperative stop, and old events mean status needs verification.
Age threshold is max(120 seconds, twice the configured cadence). Forced termination
may leave no shutdown event. No PID probing or scheduler/launchd commands.

Last success/delivery history survives restart. Errors clear at a subsequent
successful cycle or delivery as appropriate, not at a skipped slot. Diagnostic
publication is best effort; failed publication never suppresses a claim/delivery,
retries it, or changes host exit behavior. Existing stdout event allowlists stay
unchanged. No notification payload, project/site, paths, tokens or traceback in
status responses. Publication failure has a fixed stderr diagnostic; the UI may
show stale data until publication resumes.

Reader: fixed filename only, bounded regular-file reads, no symlink document;
strict schema/types/timestamps/status/reason allowlists. Invalid/unreadable state
returns unavailable with a fixed operator action, never raw file contents.
User-root isolation guard remains enforced, including Field Lab namespace rejection.
No status mutation in GET and Cache-Control no-store. Atomic replace prevents a
partial JSON view; timestamps use UTC, UI renders the reader's local time.

Tests before implementation: missing/corrupt/stale/shutdown state; bounded and
nonregular reads; restart history; disabled policy vs channel; delivery acceptance
wording; failed cycle vs skipped slot; publication failure leaves delivery intact;
read-only API, privacy allowlist, root isolation, Unicode/spaces; actual UI rendering,
refresh failure and race handling. Existing alert/host/notification/UI invariants
remain green. No Field Lab/NAS, decision/scoring, scheduler or ledger changes.

## Deployment and native checklist

Update both installed application and alert-host environment, then restart only
the alert host through its existing operator procedure. No task/LaunchAgent or
installation is performed by this PR. Application and host must use the same
user data root; custom scheduler state directories do not affect the status path.
An older host has no snapshot; an older retained snapshot may become stale.
Startup/config/import errors before observer creation are visible in the existing
logs, not guaranteed to appear here. The view does not inspect supervisor retry
budget/exhaustion directly; silence or hard stop yields stale observations.

On macOS and Windows 11: open status, compare startup configuration and cycle
completion against dedicated logs, verify disabled policy vs disabled channel,
check accepted notification wording, force a notification failure in an isolated
deployment, refresh, then cooperative stop and hard-stop stale behavior. Confirm
no claim, delivery, configuration write or service start occurs on opening or
refreshing. These are new status-view checks, not a repeat of #341 acceptance.

## Post-merge host integration verification (#342)

Main f2f2fbd3766e296eb2a509e89458be04b87faf26 already wires StatusObserver
in the production host CLI. No additional decision or publication implementation
is required. Tests in test_opportunity_alert_host_status_integration.py exercise
that wiring through the real scheduler, runner and durable ledger, with external
Tonight inputs and OS delivery substituted. They pass the host-produced snapshots
through the read-only endpoint and execute the real presentation script.

| Host boundary | Snapshot effect |
| --- | --- |
| Config loaded, host lock acquired, startup | enabled/channel/cadence; updated_at; stopped=false; retained success/delivery/error history |
| COMPLETED + NO_ALERT or ALERT_EMITTED | last_success_at and updated_at; no invented notification |
| Scheduler ERROR / cycle ERROR | scheduler_failed / cycle_failed; prior success retained |
| Notification DELIVERED | notification acceptance by OS; no visibility guarantee |
| Notification FAILED / SKIPPED | allowlisted delivery status/reason; delivery_failed only for FAILED |
| Shutdown after once or cooperative stop | stopped=true; history retained |
| Fatal error after observer creation | host_failed; existing exit behavior retained |
| Snapshot write failure | fixed stderr diagnostic; cycle/claim/delivery/exit behavior retained |
| Age exceeds max(120s, 2*cadence) | reader derives stale; host never writes a state field |

The v1 format records the successful cycle timestamp, not an alert identifier
or a claim payload. ALERT_EMITTED is verified against the existing host event
and durable ledger; no private claim data is added to the status schema.
Native deployment still requires upgrading both environments and choosing the
same user data root. These integration tests neither install nor register an OS
service. Windows CI is separate from Windows 11 GUI acceptance on Franck Testé.
