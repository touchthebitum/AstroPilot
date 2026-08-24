from dataclasses import dataclass, field
from decision.risk.risk_report import RiskReport
from decision.night_productivity.night_productivity_result import NightProductivityResult
from decision.mission.night_planner import NightTask
from decision.intelligence.analysis_result import AnalysisResult
from decision.quality.astro_quality_result import AstroQualityResult

@dataclass(frozen=True)
class MissionReason:
    title: str
    severity: str = "info"
    value: str | None = None


@dataclass(frozen=True)
class NightMission:
    target: str
    confidence: str
    reasons: list[MissionReason] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)
    window_start: str | None = None
    window_end: str | None = None
    recommended_hours: float = 0.0
    expected_gain: float = 0.0
    risk_report: RiskReport | None = None
    season_analysis: AnalysisResult | None = None 
    productivity: NightProductivityResult | None = None
    astro_quality: AstroQualityResult | None = None
    tasks: list[NightTask] = field(default_factory=list)
    night_slices: list = field(default_factory=list)
