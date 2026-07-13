def build_night_schedule(objects, available_hours, profile=None):
    schedule = []
    remaining = available_hours
    current_time = 0

    for obj in objects:
        if remaining <= 0:
            break


        ####print("\nDEBUG Scheduler")
        ###print(obj["name"])
        ##print("remaining_hours =", obj.get("remaining_hours"))
        #print("remaining =", remaining)

        remaining_hours = obj.get("remaining_hours")

        if remaining_hours is None:
            remaining_hours = remaining

        duration = min(
            remaining_hours,
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
