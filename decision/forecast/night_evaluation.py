from dataclasses import dataclass, field


@dataclass(slots=True)
class NightEvaluation:
    all_results: list
    top3: list
    best_score: float
    best_object: str
    best: dict
    setup_name: str
    night_score: float

    top_objects_for_night: list = field(default_factory=list)
