# Guardian explicit renewal UI v1

The session panel reads `/v1/executions/{execution_id}/guardian-renewal` for the
selected exact execution. Configuration remains exclusively server controlled.
The disabled status hides the panel and preserves legacy transition payloads and
headers. An unavailable or invalid status prevents a start/stop transition rather
than guessing whether Guardian is enabled.

The explicit confirmation button is available for a fresh, owned, eligible
IN_PROGRESS execution. A visual-only interval reevaluates expiry using server
clock plus monotonic elapsed browser time. It performs no network request.

Each click submits exactly one UUID and the displayed instance guard. Pending
requests disable confirmation; only accepted server timestamps change the display.
Success, including replay, is followed by a status GET. Lost responses, timeout
and malformed or ambiguous results keep the uncertainty message visible and block
confirmation until the user explicitly checks status. This GET does not prove that
a particular command committed. There is no automatic retry or same-key retry UI.

Start and closure read status for their exact execution and add the adapter's
idempotency and owner headers when enabled. The existing single transition route
remains the only mutation route. Partial server failures distinguish execution
persistence from Guardian publication; orphan executions can still be closed.

Dynamic Node tests execute the production helpers through a deterministic DOM and
transport harness. The adapter integration suite independently checks the actual
FastAPI routes and single-transition dispatch. No weather, hardware, NAS, Field Lab
or Guardian recommendation policy is modified.
