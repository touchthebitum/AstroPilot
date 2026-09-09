from dataclasses import dataclass, field
from datetime import datetime
from decision.risk.risk_report import RiskReport
from decision.night_productivity.night_productivity_result import NightProductivityResult
from decision.mission.night_planner import NightTask
from decision.intelligence.analysis_result import AnalysisResult
from decision.quality.astro_quality_result import AstroQualityResult
from decision.quality.dew_risk_result import DewRiskResult
from decision.filtering.selected_filter import SelectedFilter


class _ImmutableMissionList(list):
    def _reject_mutation(self, *args, **kwargs):
        raise TypeError("immutable_mission_collection")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    __iadd__ = _reject_mutation
    __imul__ = _reject_mutation
    append = _reject_mutation
    clear = _reject_mutation
    extend = _reject_mutation
    insert = _reject_mutation
    pop = _reject_mutation
    remove = _reject_mutation
    reverse = _reject_mutation
    sort = _reject_mutation


def _immutable_mission_list(values):
    if isinstance(values, _ImmutableMissionList):
        return values
    return _ImmutableMissionList(values)

@dataclass(frozen=True)
class MissionReason:
    title: str
    severity: str = "info"
    value: str | None = None


@dataclass(frozen=True)
class NightMission:
    target: str
    confidence: float | str | None
    reasons: list[MissionReason] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)
    window_start: datetime | None = None
    window_end: datetime | None = None
    recommended_hours: float = 0.0
    expected_gain: float = 0.0
    risk_report: RiskReport | None = None
    season_analysis: AnalysisResult | None = None 
    productivity: NightProductivityResult | None = None
    astro_quality: AstroQualityResult | None = None
    dew_risk: DewRiskResult | None = None
    tasks: list[NightTask] = field(default_factory=list)
    night_slices: list = field(default_factory=list)
    selected_filter: SelectedFilter | None = None
    mission_id: str | None = None
    decision_id: str | None = None
    selection_id: str | None = None
    site_name: str | None = None

    def __post_init__(self):
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("mission_target_required")

        for name in ("reasons", "equipment", "night_slices"):
            object.__setattr__(
                self,
                name,
                _immutable_mission_list(getattr(self, name)),
            )

        timeline = getattr(self.productivity, "timeline", None)
        if (
            timeline is not None
            and getattr(timeline, "slices", None) is not None
            and self.night_slices == timeline.slices
        ):
            object.__setattr__(timeline, "slices", self.night_slices)

        provenance = (self.mission_id, self.decision_id, self.selection_id)
        if any(value is not None for value in provenance):
            if any(
                not isinstance(value, str) or not value.strip()
                for value in provenance
            ):
                raise ValueError("mission_provenance_required")
            if (
                not self.equipment
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in self.equipment
                )
                or not isinstance(self.site_name, str)
                or not self.site_name.strip()
            ):
                raise ValueError("mission_identity_required")
