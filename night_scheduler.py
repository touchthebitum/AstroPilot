def build_night_schedule(objects, available_hours, profile=None):
    schedule = []
    remaining = available_hours
    current_time = 0

    for obj in objects:
        if remaining <= 0:
            break

        duration = min(
            obj.get("remaining_hours", remaining),
            remaining
        )

        schedule.append({
            "object": obj["name"],
            "hours": duration,
            "start": current_time,
            "end": current_time + duration,
            "score": obj.get("global_score", obj.get("score", 0)),
            "setup": obj.get("best_setup"),
        })

        remaining -= duration
        current_time += duration

    return schedule
