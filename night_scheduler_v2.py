from dataclasses import dataclass
from typing import List


def normalize_time(t):
    return t + 24 if t < 12 else t

@dataclass
class NightEvent:
    start: float
    end: float
    event_type: str
    description: str
    object_name: str | None = None
    setup: str | None = None
    filter_name: str | None = None


class NightSchedulerV2:

    def __init__(self):
        self.events: List[NightEvent] = []

    def add_event(
        self,
        start,
        end,
        event_type,
        description,
        object_name=None,
        setup=None,
        filter_name=None,
    ):
        self.events.append(
            NightEvent(
                start,
                end,
                event_type,
                description,
                object_name,
                setup,
                filter_name,
            )
        )

    def get_events(self):
        return sorted(
        self.events,
        key=lambda event: (normalize_time(event.start), normalize_time(event.end))
    )
        
if __name__ == "__main__":

    scheduler = NightSchedulerV2()

    scheduler.add_event(
        22.30,
        22.35,
        "AUTOFOCUS",
        "Autofocus initial"
    )

    scheduler.add_event(
        22.35,
        0.35,
        "OBSERVATION",
        "Observer IC1396",
        object_name="IC1396",
        setup="Samyang135_2600",
        filter_name="Ha"
    )

    scheduler.add_event(
        0.35,
        0.38,
        "FILTER_CHANGE",
        "Passage OIII"
    )

    scheduler.add_event(
        0.38,
        2.10,
        "OBSERVATION",
        "Observer IC1396",
        object_name="IC1396",
        setup="Samyang135_2600",
        filter_name="OIII"
    )

    for event in scheduler.get_events():
        print(event)

    def normalize_time(t):
        return t + 24 if t < 12 else t