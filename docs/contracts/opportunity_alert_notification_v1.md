# Opportunity Alerts notification channel v1

## Boundary and channel choice

Delivery consumes a claimed ALERT_EMITTED cycle after scheduler.poll returns.
Tonight, scoring, runner, scheduler and the decision/alert ledger remain unchanged.
NO_ALERT and ERROR cycles never notify. A scheduler state-write error may contain an
already claimed ALERT_EMITTED cycle: that claim still receives one delivery attempt.

A small OpportunityAlertNotifier protocol takes an immutable public payload.
The allowlist is project_key, site_name, window_start, window_end, expected_gain.
No lineage IDs, idempotency keys, evidence, profile, coordinates or diagnostics
cross this boundary. Projection formats existing values; it computes no opportunity.

V1 uses macOS osascript display notification: installed OS tooling, no extra
package, no cloud credentials, and an injectable process boundary for tests.
A fixed AppleScript reads title/message from argv. The process is invoked directly
at /usr/bin/osascript, without shell or dynamic script interpolation, with UTF-8,
no captured output and a five-second timeout. Other platforms return SKIPPED.
An explicit disabled channel is the default. Native framework integration would
require extra deployment/identity management; email/push/webhook are outside V1.

## Delivery results

- DELIVERED / accepted_by_os: osascript exited zero. This is OS submission, not
  proof of a visible banner or user acknowledgement. Permissions, Focus and the
  logged-in GUI session can prevent display even after acceptance.
- FAILED: invalid payload, timeout, process error, or notifier failure. Reasons
  are stable allowlisted codes; exception/process output is never logged.
- SKIPPED: disabled channel or unsupported platform; no process is launched.

The host reports a separate notification event with only status and reason.
ALERT_EMITTED continues to mean claimed, regardless of delivery outcome.
Delivery cannot mutate or reset the ledger or scheduler watermark. There is one
attempt per returned claimed cycle, no retries, no persistent outbox, and no
notifier deduplication. Duplicate/restart suppression remains in the existing
ledger and scheduler. Replaying a cycle manually is outside the host contract.
A crash after claim and before/during delivery can lose a notification.
Claim at-most-once is not delivery guaranteed. Delivery failure does not change
host decision status or cause process restart; later cycles continue normally.

## Installation and user text

Existing schema_version 1 host JSON remains valid. Optional
`"notification_channel": "macos"` opts into delivery; `"disabled"` or omission
skips delivery. Unknown channels/config keys fail before starting the host.
This also works with the existing LaunchAgent config path; no LaunchAgent change
or installation is needed in this PR.

Title: `AstroPilot — <project_key>`.
Message: `<site_name> · <start> – <end> UTC · Gain attendu : <expected_gain>`.
Times explicitly use UTC; values come only from the public payload. Text is
bounded and control characters normalized for presentation, without interpreting
quotes, backslashes, Unicode or other characters as commands.

Test with injected backends; no real notification is sent during automated tests.
Manual macOS validation requires an opted-in GUI session and notification settings
for the OS script host. Inspect separate notification events in host stdout.

After merge choose either a Windows channel or durable outbox/bounded retries,
according to operational evidence; do not combine both in the next PR.
