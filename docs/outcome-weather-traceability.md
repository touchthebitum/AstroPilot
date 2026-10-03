# Outcome weather traceability

The Outcome GET and POST projections expose historical forecast provenance without
changing evaluation identities, comparison selection, errors, scoring, or serialized
OutcomeEvaluation/DecisionForecastEvidence documents.

## Additive API fields

- `results[].forecast_point`: null for a result without a persisted forecast point.
  Otherwise `selected_forecast_for_utc` (UTC ISO timestamp) and
  `temporal_offset_minutes` (signed number, forecast time minus observation time).
- `weather_traceability`: summary containing `provider_id`, `model_id`,
  `retrieved_at_utc`, `requested_location`, `grid_location`, and
  `temporal_offset_convention` (`forecast_time - observed_time`).
- Locations are null or `{latitude, longitude, altitude_m}`; altitude can be null.
- Provider, model and retrieval timestamp are summarized when shared by all
  comparable results. When they differ, the summary fields are null and these
  fields are retained in each result's `forecast_point`.
- When coordinate pairs differ across results, they are retained per result
  instead of assigning one result's coordinates to the whole evaluation.

The persisted comparison already contains provider, model, retrieval timestamp,
selected forecast timestamp and offset. The prior API omitted all of them.
Coordinates remain in DecisionForecastEvidence and are recovered by exact
provider/model/retrieval/valid-time/variable/unit/value matching. This is a lookup,
not nearest-point selection. Missing evidence, no match, or multiple distinct
coordinate pairs yields null coordinates. No provider/model/location is invented.
Unreadable/corrupt evidence follows the existing API error handling.

## UI and compatibility

The existing primary comparison remains followed by a separate text section,
“Traçabilité de la prévision”. Dates use the observation editor's site timezone
when available and also show UTC; otherwise UTC is shown. No historical site
timezone is inferred from coordinates. Unknown values show “Non disponible”.
Old persisted evaluations require no migration. The UI still accepts older API
projections lacking the additive fields. Persistence contract tests cover the
existing serialized format.

## Synthetic example

Observation: 2026-10-03 00:10 Europe/Zurich = 2026-10-02 22:10 UTC.
Selected point: 2026-10-03 00:00 Europe/Zurich = 2026-10-02 22:00 UTC.
Offset: -10 min. RH forecast: 91%; observation: 73%; signed error: +18 points.
Provider: Open-Meteo; model: unavailable. Requested: 46.75, 6.55.
Grid: 46.76, 6.56; grid altitude: 1200 m. Retrieval: 2026-10-02 18:10 UTC.
These values are synthetic and make no claim about an actual Buttes forecast.

The regression fixture exercises orchestration, persistence replay, POST/GET API,
Node UI rendering, absent evidence and ambiguous coordinates.
