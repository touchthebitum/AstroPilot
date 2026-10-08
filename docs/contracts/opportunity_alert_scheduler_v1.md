# Opportunity Alert Scheduler v1

One scheduler identity binds one user/context, one fixed cadence and one dedicated
state directory. Default cadence: one hour, anchored at Unix epoch UTC. Polling
uses an injected aware clock; logical_time is the start of the current UTC slot.
No polling before the anchor. Intervals must be positive integral seconds.

Only the current slot is eligible: missed slots are discarded, never replayed in
bursts. Repeated or backward slots are skipped. Cadence changes require a new
state directory; mismatched configuration fails closed.

The store is independent of the alert ledger. A shared local-filesystem lock is
held across reservation, runner invocation and completion. Concurrent instances
serialize and recheck durable state before invoking the runner. An instance also
rejects concurrent/reentrant polling immediately with OVERLAP. No next runner
starts while a previous runner holds the shared lock.

Persist last_started_slot BEFORE calling the runner, and last_completed_slot plus
status/reasons AFTER it returns. Atomic replace and fsync follow the existing
ledger pattern. A crash after reservation sacrifices that slot (at-most-once
attempt); the next slot remains eligible. A write failure prevents invocation or
returns a scheduler ERROR, without resetting state. Corruption fails closed.
The alert ledger remains the authority for durable alert suppression.

Runner ERROR and unexpected runner exceptions complete the slot with ERROR.
No immediate retry; later slots remain eligible. Results distinguish COMPLETED,
SKIPPED, OVERLAP and ERROR, and carry the runner result when available. Persist
only status/reasons, never alert payload or profile. Disabled policy still reaches
the runner's cheap NO_ALERT path, without Tonight evaluation or alert claim.

The scheduler only calls run_cycle(policy, logical_time, **inputs). Input acquisition
is the caller's responsibility. No weather/moon/ranking/gain logic, delivery,
Field Lab/NAS dependency, daemon, cron, launchd, Docker or background loop.
A future host polls this service and supplies current inputs; this PR defines the
application orchestration contract, not process startup or deployment.

## Integration example

```python
scheduler = OpportunityAlertScheduler(
    runner=existing_runner,
    directory=user_context_scheduler_directory,
    clock=lambda: datetime.now(timezone.utc),
    cadence=SchedulerCadence(interval=timedelta(hours=1)),
)
# A future host invokes poll repeatedly; the scheduler determines eligibility.
result = scheduler.poll(policy=current_policy, **current_tonight_inputs)
```

The directory must be stable across restarts and exclusive to the same
user/context. Distinct contexts require distinct directories. Shared network
filesystems and distributed leases are outside V1. Shared-instance calls can
block until the active cycle finishes; hosts must not accumulate an unbounded
queue of polling calls. Input acquisition should be lazy in the host when disabled.
Only the latest completion is retained; this is a watermark, not an audit history.
