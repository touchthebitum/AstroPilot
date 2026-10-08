# Opportunity Alerts Windows notification channel v1

## Contract (written before implementation)

Opt in with `"notification_channel": "windows"` in the existing schema-version 1
host JSON. Omission/disabled and macos keep their existing behavior. Only backend
selection changes in the host; decision, runner, scheduler, API and ledger do not.
The existing OpportunityAlertNotifier consumes exactly NotificationPayload's five
public fields. ALERT_EMITTED remains a claim. NO_ALERT/ERROR never notify; an
already claimed cycle inside a scheduler error still receives one attempt.

Use Windows 11's native notification-area balloon API Shell_NotifyIconW, via a
fixed Windows PowerShell 5.1 script and framework P/Invoke. No extra Python,
PowerShell module, AppUserModelID, shortcut/registry installation, COM activator,
cloud service or Task Scheduler. Windows App SDK toasts require extra deployment
and identity machinery. WinForms NotifyIcon hides the native return value, so V1
calls Shell_NotifyIconW directly and checks both add and notification submission.
A temporary invisible WinForms window owns the icon; dispose it after ten seconds.
This is an ephemeral notification, with no action, activation or promised history.
Deleting the icon can dismiss a notification still queued/displayed. The ten-second
lifetime is a bounded resource policy, not a guarantee of banner duration.

Launch the OS PowerShell executable by absolute SystemRoot path, with argv,
NoProfile/NonInteractive/STA/hidden and a fixed UTF-16LE EncodedCommand. No shell,
execution-policy bypass, user script interpolation or executable PATH lookup.
Title/message travel only as ASCII JSON on stdin (escaped Unicode). Source and
argv are independent of public text. Respect native WCHAR capacities (63/255 UTF-16
units) without splitting surrogate pairs. Reuse the existing UTC/gain formatting.
Process output is discarded; timeout is 20 seconds including compile/startup and
ten-second icon lifetime. A timeout kills/waits the PowerShell child; framework
compilation may launch the system C# compiler. There is no delivery subprocess,
background notification helper or retry after timeout.

## Results and invariants

DELIVERED / accepted_by_os: child exit zero after both native calls returned true.
It means API acceptance only, not visible display or user acknowledgement. Focus,
notification settings, Explorer and an interactive desktop affect visibility.
FAILED / process_failed: missing PowerShell/framework/native API/desktop, OS-call
rejection, invalid OS path or nonzero exit; FAILED / delivery_timeout on timeout.
FAILED / invalid_payload and notifier_failed retain the existing meanings.
Selecting windows on another platform returns FAILED / process_failed (requested
backend unavailable), without launching anything. Disabled remains SKIPPED. macOS
unsupported-platform semantics are unchanged.

One attempt, no retry, re-claim, reset, outbox or notifier deduplication. Delivery
results remain separate from claims and never modify business values or state.
Field Lab/NAS, macOS backend and autostart are outside this change.

## Evidence and native acceptance

References: [Shell_NotifyIconW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shell_notifyiconw),
[NOTIFYICONDATAW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-notifyicondataw),
[notification area](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area),
[desktop toast identity](https://learn.microsoft.com/en-us/windows/win32/shell/quickstart-sending-desktop-toast).

**native acceptance pending**: development on macOS; isolated process mocks cannot
prove native marshaling, PowerShell parsing or Windows 11 display. Automated tests
must never send real notifications. No CI restructuring in V1. The existing Windows
Actions job runs the adapter tests plus a harmless native PowerShell parser and
C# structure compilation/size check; it never sends a notification. Actual native
API acceptance and visible behavior still require the interactive checklist.

Windows 11 checklist (interactive user, x64 and supported ARM64 if applicable):
- Opt in, submit one claimed cycle; verify title/site/UTC/gain and one banner.
- Verify native add/modify success yields DELIVERED; no acknowledgement assumed.
- Verify icon disappears after ten seconds, process exits, no extra window remains.
- Exercise accents, emoji, quotes, backslashes, XML characters and shell syntax.
- Disable notifications/Focus: document suppression with API-acceptance semantics.
- Stop Explorer/noninteractive session, deny PowerShell or framework, force timeout:
  verify FAILED without private process output, retry or ledger changes.
- Restart after claim/failure: confirm existing suppression; NO_ALERT/ERROR silent.
- Default disabled and macos regression stay unchanged; inspect installed wheel.

After merge choose Windows autostart/Task Scheduler OR durable outbox/bounded retry
according to priority, as a separate PR.
