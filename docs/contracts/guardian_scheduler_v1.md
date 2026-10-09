# Guardian scheduler v1

Scheduling only: the injected GuardianPeriodicRunner remains the sole evaluation path.
No service call, network, hardware, notification, live API, host loop, or business dependency.

## Cadence and clock

GuardianSchedulerCadence requires an explicit positive integral-second interval and
an aware anchor, normalized to UTC. Version: guardian-scheduler-v1.
slot(t) is anchor + floor((UTC(t) - anchor) / interval) * interval;
before anchor it is None. The injected clock is read once per poll. Naive/invalid
time raises ValueError before reservation/acquisition. logical_time is always the
UTC slot start, independent of poll jitter and timezone representation.

## Reservation, overlap and recovery

poll() invokes run_cycle(logical_time=slot) at most once per increasing slot within
one scheduler instance. A nonblocking lock covers reservation and the whole cycle.
Concurrent polls return SKIPPED/cycle_in_progress without queuing. An overlap does
not reserve the new slot: it may run on a later poll if still current. Repeated or
older slots return SKIPPED/slot_already_reserved, including clock rollback.
Reserve before invocation, release the lock in finally. Exceptions and ERROR cycle
results consume the slot and return ERROR/cycle_error; future slots remain eligible.
No immediate retry. Process-control exceptions propagate, retaining the reservation
and releasing the lock. Invalid runner results are cycle errors (including a result
with the wrong logical_time or status). No exception text escapes in reasons.

Downtime skips all missed slots: only the current slot is considered on each poll.
No loop, burst or backfill. Before anchor: SKIPPED/before_anchor.
Successful assessment: COMPLETED/cycle_completed. A completed assessment may still
be fail-closed; scheduler status never replaces cycle.decision_eligible/action.
Result is immutable with status, slot, allowlisted reason, optional cycle, version.

## Persistence boundary

V1 is explicitly in-memory, one instance/owner per context. No restart or multi-
instance deduplication claim: recreating the scheduler can replay the current slot.
This cannot trigger external actions in this PR; assessment is read-only. A dedicated
versioned Guardian watermark and nonblocking shared lock are required before a
persistent host, multiple owners, notifications or hardware consumers are introduced.
Never reuse Opportunity Alerts state or user_profile. Opportunity Alerts was audited
as a pattern only; its blocking file lock and business-specific store are not imported.

## Next step

Guardian host/process with dedicated durable reservation, lifecycle and restart tests;
no automatic material action. Notification authority requires a separate contract.
