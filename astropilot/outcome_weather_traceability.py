"""Read-only provenance projection; never selects or recomputes forecast points."""


def weather_traceability(evaluation, evidence_store):
    comparison = evaluation.comparison
    evidence = evidence_store.load(decision_id=comparison.decision_id)
    points = {}
    locations = {}
    for result in comparison.results:
        source = result.forecast_point
        if source is None:
            continue
        value = (result.forecast_value if hasattr(result, "forecast_value")
                 else result.forecast_coverage_percent)
        matches = [] if evidence is None else [p for p in evidence.forecast_points
            if p.provider_id == source.provider_id and p.model_id == source.model_id
            and p.retrieved_at_utc == source.retrieved_at_utc
            and p.forecast_for_utc == source.forecast_for_utc
            and any(v.variable == result.variable and v.unit == result.unit
                    and v.value == value for v in p.values)]
        pairs = {(p.requested_location, p.grid_location) for p in matches}
        pair = next(iter(pairs)) if len(pairs) == 1 else (None, None)
        locations[result.variable.value] = pair
        points[result.variable.value] = {
            "selected_forecast_for_utc": source.forecast_for_utc.isoformat(),
            "temporal_offset_minutes": source.temporal_offset.total_seconds() / 60,
            "retrieved_at_utc": source.retrieved_at_utc.isoformat(),
            "provider_id": source.provider_id,
            "model_id": source.model_id,
        }
    # Coordinates shared by every comparable result belong to the summary.
    pairs = set(locations.values())
    common = next(iter(pairs)) if len(pairs) == 1 else (None, None)
    def location(value):
        return None if value is None else {
            "latitude": value.latitude, "longitude": value.longitude,
            "altitude_m": value.altitude_m,
        }
    summary = {
        "requested_location": location(common[0]),
        "grid_location": location(common[1]),
        "temporal_offset_convention": "forecast_time - observed_time",
    }
    if len(pairs) > 1:
        for variable, pair in locations.items():
            points[variable]["requested_location"] = location(pair[0])
            points[variable]["grid_location"] = location(pair[1])
    for key in ("provider_id", "model_id", "retrieved_at_utc"):
        values = {point[key] for point in points.values()}
        summary[key] = next(iter(values)) if len(values) == 1 else None
        if len(values) == 1:
            for point in points.values():
                del point[key]
    return {"points": points, "summary": summary}
