# Guardian notification v1

Notification is presentation, never execution. The notifier consumes an immutable,
already evaluated ASSESSED cycle. It cannot evaluate Guardian, change risk, action,
applicability, thresholds, or scheduler state. ERROR cycles are not assessments
and are skipped; existing host error diagnostics remain authoritative.

Policy version `guardian-notification-v1`: disabled by default, explicit minimum
risk `WARNING` by default. Enabled policy compares SAFE < WATCH < WARNING <
CRITICAL < UNKNOWN. Any level including SAFE can be selected explicitly. Channel
is `local`; no cloud, email, webhook, mobile, outbox, retry or hardware consumer.
Host configuration may include `notification` with `version`, `enabled`, and
`min_level` (enum name). Unknown fields/versions/levels are rejected.

Public payload: risk_level, recommended_action, session_state,
action_applicability, allowlisted weather reason codes, assessed_at and
logical_time. No source evidence, session identifier, provider prose, paths,
exceptions or secrets. Unrecognized reasons are omitted. No site is necessary.
UNKNOWN explicitly says evidence is uncertain and EMERGENCY_STOP is a recommendation.
Every message says no action was executed and displays applicability.

One bounded synchronous OS attempt after a COMPLETED scheduler result. Durable
reservation/completion happens before delivery: restart/same-slot replay cannot
retry notifications. Best effort, at most once per reserved slot; crash between
completion and delivery may lose a notification. Failure never changes the
assessment or watermark. No second deduplication store.

Delivery is independently DELIVERED / FAILED / SKIPPED with fixed reason codes.
DELIVERED means OS accepted the request, not visible/read/acknowledged. macOS uses
fixed AppleScript source and argv data, timeout 5 seconds. Windows uses fixed
encoded PowerShell source, ASCII JSON stdin, Shell_NotifyIconW, bounded 10-second
owner lifetime, timeout 20 seconds. shell=False, suppressed child diagnostics,
no activation handlers. Unsupported platforms skip. Interactive OS session and
notification permissions/preferences can affect visibility.

Local transport primitives mirror the validated Opportunity Alerts mechanism in
an independent module; Opportunity classes and behavior are unchanged. Native
CI checks adapter semantics with injected processes without sending notifications.
Manual visible acceptance on macOS/Windows is required after merge before any
outbox/retry or separate future hardware consumer is considered.

## Configuration example

Add to the existing Guardian host configuration to opt in explicitly:

```json
"notification": {
  "version": "guardian-notification-v1",
  "enabled": true,
  "min_level": "WARNING"
}
```

Absent configuration preserves the existing silent host behavior. Changing this
policy affects presentation only. UNKNOWN remains above CRITICAL for notification
selection; this ordering does not imply a newly evaluated physical risk.
