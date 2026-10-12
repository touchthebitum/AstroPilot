"""Shared operating thresholds for admission and locked publications."""
# Proposed six-week envelope: 17,999 existing + 42 * 5,000 new artifacts.
# NAS throughput/disk/recovery validation is required before deployment.
OPERATIONAL_SOFT_LIMIT = 300_000
RESERVED_BUDGET = 15_000
WARNING = .80
STOP = .90


def capacity_policy(max_artifacts):
    soft_limit = min(max_artifacts, OPERATIONAL_SOFT_LIMIT)
    stop_at = int(soft_limit * STOP)
    reserve = min(RESERVED_BUDGET, max(0, stop_at // 6))
    return dict(operational_soft_limit=soft_limit, stop_at=stop_at,
                reserved_budget=reserve, effective_stop_at=stop_at-reserve)
