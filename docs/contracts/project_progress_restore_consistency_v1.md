# Project progress credit consistency after restoration v1

A project progress view must not count credits that the session view rejects.
`GET /v1/projects/{project_id}/progress` now validates all contributing credits
against the same execution, mission/selection provenance, evidence and duration
checks used by session reads before calculating or returning the projection.
`PUT` performs this check after its existing revision check and before mutating
or saving the profile. Inconsistent/missing/corrupt contributing lineage returns
HTTP503 `detail.code=project_credit_inconsistent`. No partial progress is returned
and no profile edit is committed in this case. No automatic repair, deletion,
re-credit, baseline or retry is introduced.

Each contributing intent is validated once per project read using the existing
session validator and, when supported, the validated acceptance read snapshot.
Projects without credits retain their existing profile-only behavior; credits
in another project do not trigger this additional project-scoped check. Existing
profile structural corruption, stale revision conflicts, credit immutability and
manual-progress validation remain unchanged. Session reads retain their current
intent-scoped semantics: an unrelated invalid intent does not invalidate a
valid session's own historical projection.

Qualification uses stopped synthetic writers, an independently frozen relative
path/size/SHA256 inventory and new restore destinations. Positive restored graphs
must preserve totals, IDs, revision and `already_applied` replay. Missing or
altered snapshots are rejected by the qualification's external manifest before
activation; runtime corruption is separately probed through the real API.
A trusted manifest is a qualification precondition, not a newly shipped backup
API, an authenticity signature or a guarantee for a live multi-store copy.
The local history cursor key is outside logical history backup; the normal
application regenerates it in the new destination. Guardian runtime attestations
are not copied and restarting a caller never restores renewal ownership.
No private keys, real profile or critical stash are uploaded or modified.
