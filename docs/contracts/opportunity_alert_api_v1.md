# Opportunity Alerts API v1

Baseline: #331 and #332; policy and ledger schema 1.

## HTTP boundary

POST /v1/tonight accepts strict boolean `claim_opportunity_alert` (default false).
When true, the server passes the exact live TonightResult from that request to
OpportunityAlertService once, after Tonight transport validation. No additional
weather, moon, ranking, productivity or gain evaluation takes place. A separate
evaluate endpoint would require a live-result cache or a second Tonight run;
therefore this increment uses the existing composition boundary.

The request cannot configure or enable policy. The composition root supplies a
trusted policy provider; production defaults to OpportunityAlertPolicy() (disabled).
Policy persistence/configuration is outside this increment.

An omitted/false flag returns no `opportunity_alert` field and makes no ledger
claim. A true flag returns `opportunity_alert`: status `alert` or `no_alert`,
`reason_codes` faithfully copied from the internal decision, schema_version 1,
policy_version 1, and nullable `alert`. NO_ALERT never contains an alert.

The allowlisted alert contains alert_id (opaque internal SHA256 key), project_key,
imaging_field_id, acquisition_intent_id, site, window_start/end, duration_minutes,
expected_gain, decision_score and logical_time. All times are normalized to UTC.
The internal service permits only complete decision-eligible AQI, so decision_score
is authoritative. Duration is copied; recommended_hours is omitted because the
internal alert does not carry it. No mission/selection/decision lineage, filter,
weather, lunar evidence or legacy payload is exposed in this subdocument.

A claim commits durably before ALERT is transported. Retries can return NO_ALERT
(duplicate_or_cooldown); this is at-most-once, not guaranteed delivery. Restart
preserves suppression. Ledger corruption/unavailability returns HTTP 503 with
`detail.code = opportunity_alert_ledger_unavailable`, no alert and no reset.
An existing Tonight HTTP weather refusal returns 409 with
`opportunity_alert_tonight_refused` before any claim; no weather is reevaluated.
No GET replay, scheduler, notification, Field Lab or NAS changes.
