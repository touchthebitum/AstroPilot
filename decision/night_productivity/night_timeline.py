from dataclasses import dataclass, field

from decision.night_productivity.night_slice import NightSlice


@dataclass(frozen=True)
class NightTimeline:
    slices: list[NightSlice] = field(default_factory=list)