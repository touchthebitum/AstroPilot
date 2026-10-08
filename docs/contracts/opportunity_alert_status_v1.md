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
