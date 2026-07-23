from dataclasses import dataclass, field

@dataclass
class Candidate:
    name: str
    catalog_key: str

    priority: float
    astro_score: float
    final_score: float
    decision_score: float

    season_bonus: float
    altitude_bonus: float
    roi: float
    portfolio_score: float

    global_score: float
    setup_score: float
    best_setup: str | None

    completion_bonus: float
    closure_bonus: float

    postponement_risk: float
    postponement_penalty: float
    urgency_bonus: float
    postponement_net_impact: float
    postponement_reason: str

    reasons: dict = field(default_factory=dict)
    strategy_scores: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)
