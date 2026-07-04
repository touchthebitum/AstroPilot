from dataclasses import dataclass, field


@dataclass(frozen=True)
class MissionReason:
    title: str
    severity: str = "info"
    value: str | None = None


@dataclass(frozen=True)
class MissionStep:
    time: str
    title: str


@dataclass(frozen=True)
class NightMission:
    target: str
    confidence: float

    reasons: list[MissionReason] = field(default_factory=list)
    timeline: list[MissionStep] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)

    expected_gain: float = 0.0
    next_mission: str | None = None
