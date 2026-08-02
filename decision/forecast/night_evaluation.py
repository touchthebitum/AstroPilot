from dataclasses import dataclass



@dataclass(slots=True)
class NightEvaluation:
    all_results: list

    top3: list

    best_score: float

    best_object: str

    best: dict

    setup_name: str

    night_score: float