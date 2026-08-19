from dataclasses import dataclass, field

@dataclass
class Candidate:
    name: str
    catalog_key: str

    priority: float
    astro_score: float
    final_score: float
    decision_score: float

    roi: float
    portfolio_score: float

    global_score: float
    setup_score: float
    best_setup: str | None

    closure_bonus: float

    acquired_hours: float = 0.0
    reasons: list[str] = field(default_factory=list)
    strategy_scores: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)
