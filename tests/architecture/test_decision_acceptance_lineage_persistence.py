import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

import astropilot.decision_acceptance_lineage_store as store_module
from astropilot.decision_acceptance_lineage_store import (
    FileDecisionAcceptanceLineageStore,
)
from decision.acceptance_lineage_persistence import (
    AcceptanceLineageConflictError,
    AcceptanceLineageCorruptionError,
    AcceptanceLineageNotFoundError,
    deserialize_decision_acceptance_context,
    deserialize_night_mission,
    deserialize_user_selection,
    serialize_decision_acceptance_context,
    serialize_night_mission,
    serialize_user_selection,
)
from decision.filtering.selected_filter import SelectedFilter
from decision.intelligence.analysis_result import AnalysisResult
from decision.mission.night_mission import MissionReason, NightMission
from decision.mission.night_planner import NightTask
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.context.decision_context import DecisionContext
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.context.preferences_context import PreferencesContext
from decision.models.context.session_context import SessionContext
from decision.models.context.site_context import SiteContext
from decision.models.context.sky_context import SkyContext
from decision.models.context.weather_context import WeatherContext
from decision.models.equipment.camera import Camera
from decision.models.equipment.imaging_filter import ImagingFilter
from decision.models.equipment.imaging_optics import ImagingOptics
from decision.models.equipment.imaging_setup import ImagingSetup
from decision.models.equipment.mount import Mount
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.models.sky.celestial_object import CelestialObject
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_slice import NightSlice
from decision.night_productivity.night_timeline import NightTimeline
from decision.night_productivity.night_window import NightWindow
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.opportunity.opportunity_reason import OpportunityReason
from decision.quality.astro_quality_result import AstroQualityResult
from decision.quality.dew_risk_result import DewRiskResult
from decision.recommendation.recommendation import Recommendation
from decision.risk.risk_report import RiskReport
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceContext,
)
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
)


START = datetime(2026, 9, 12, 20, 30, tzinfo=timezone.utc)
END = datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc)


def candidate(catalog_key="M31"):
    return Candidate(
        name="Andromeda Galaxy",
        catalog_key=catalog_key,
        priority=9.0,
        astro_score=8.5,
        final_score=8.1,
        decision_score=7.9,
        portfolio_score=7.5,
        global_score=8.0,
        setup_score=9.0,
        best_setup="widefield",
        closure_bonus=0.5,
        acquired_hours=2.0,
        provenance=CandidateProvenance.PROJECT,
        reasons=["high_altitude"],
        strategy_scores={"completion": 0.8},
    )


def decision_context():
    setup = ImagingSetup(
        mount=Mount("Sky-Watcher", "HEQ5", 14.0),
        optics=ImagingOptics("Askar", "FRA300", 300.0, 60.0, 5.0),
        camera=Camera("ZWO", "ASI533MM", 3.76, 3008, 3008, True),
        filter=ImagingFilter("Antlia", "Ha", "narrowband", 3.0, 656.3),
    )
    return DecisionContext(
        session=SessionContext(START, END, END - START, is_remote=True),
        site=SiteContext(
            "Mont Sujet", 47.1, 7.1, 1382.0, 4, sqm=21.3,
            has_horizon_profile=True,
        ),
        equipment=EquipmentContext(setup),
        weather=WeatherContext(
            15.0, 62.0, 8.0, seeing_arcsec=1.7, transparency=0.85,
            visibility=25.0, temperature_c=7.0, forecast_confidence=0.9,
        ),
        sky=SkyContext(
            CelestialObject("Andromeda Galaxy", "galaxy", 190.0),
            0.2, 80.0, 55.0, True,
        ),
        portfolio=PortfolioContext(2, 18.0, 9, 0.4, 4.0, 1.5),
        preferences=PreferencesContext(0.6, 0.4, 25.0, 20.0),
    )


def context(decision_id="decision-1"):
    source = candidate()
    typed_context = decision_context()
    return DecisionAcceptanceContext(
        decision_context=UserSelectionDecisionContext(
            decision_id=decision_id,
            primary_catalog_key="M31",
            exposed_alternative_catalog_keys=("M42",),
            explicitly_evaluated_catalog_keys=("M31", "M42", "M33"),
        ),
        recommendation=Recommendation(
            opportunity=Opportunity(
                action=Action.CONTINUE_PROJECT,
                candidate=source,
                reasons=[OpportunityReason("Strong", "Good conditions")],
                shortlist_entries=(source, candidate("M42")),
            ),
            confidence=0.91,
        ),
        night={
            "top_objects": [
                {
                    "catalog_key": "M31",
                    "name": "Andromeda Galaxy",
                    "decision_context": typed_context,
                }
            ],
            "object_evaluations": {
                "M31": {
                    "decision_context": typed_context,
                    "score_components": (8.5, 7.9),
                }
            },
            "selected_window": (START, END),
        },
        profile={
            "active_equipment": "widefield",
            "available_equipment": ["widefield"],
            "projects": {"M31": {"hours": 2.0, "target_hours": 20.0}},
        },
        availability=SessionAvailability(
            SessionAvailabilityMode.FIXED_WINDOW,
            start=START,
            end=END,
        ),
    )


def selection(
    source=UserSelectionSource.PRIMARY_RECOMMENDATION,
    *,
    selection_id="selection-1",
    decision_id="decision-1",
):
    targets = {
        UserSelectionSource.PRIMARY_RECOMMENDATION: "M31",
        UserSelectionSource.ALTERNATIVE: "M42",
        UserSelectionSource.OTHER_EVALUATED_TARGET: "M33",
        UserSelectionSource.DECLINED: None,
    }
    return UserSelection(
        selection_id=selection_id,
        decision_id=decision_id,
        selected_catalog_key=targets[source],
        source=source,
        selected_at=START - timedelta(minutes=15),
    )


def night_slice():
    return NightSlice(
        20.5, 21.0, 55.0, 120.0, -5.0, 80.0, 0.1,
        15.0, 62.0, 8.0, 1.7, 21.3, 8.5, 8.0, 7.8,
    )


def mission(
    *,
    mission_id="mission-1",
    decision_id="decision-1",
    selection_id="selection-1",
):
    slice_value = night_slice()
    return NightMission(
        target="Andromeda Galaxy",
        confidence="HIGH",
        reasons=[MissionReason("Excellent altitude", "info", "55°")],
        equipment=["widefield"],
        window_start=START,
        window_end=END,
        recommended_hours=3.5,
        expected_gain=1.25,
        risk_report=RiskReport("low", 1, ["stable"], {"wind": 8.0}),
        season_analysis=AnalysisResult(
            "season", "favorable", 0.92, {"months": (9, 10)}
        ),
        productivity=NightProductivityResult(
            4.0, 3.5, 0.9, 0.2, 0.1, 0.1, 0.1,
            windows=[NightWindow(20.5, 24.5, 0.9, 55.0, 15.0, 0.1, 1.7, True, "clear")],
            timeline=NightTimeline([slice_value]),
            display_start_hour=20,
        ),
        astro_quality=AstroQualityResult(8.5, 0.9, "moon", {"sqm": 21.3}),
        dew_risk=DewRiskResult(3.0, 4.0, "low", 0.2),
        tasks=[NightTask("20:00", "20:20", "Setup", "Polar align", 2, 0.0)],
        night_slices=[slice_value],
        selected_filter=SelectedFilter("Ha", "narrowband", 3.0, "profile"),
        mission_id=mission_id,
        decision_id=decision_id,
        selection_id=selection_id,
        site_name="Mont Sujet",
    )


def assert_round_trip(value, serialize, deserialize):
    restored = deserialize(serialize(value))
    assert restored == value
    assert type(restored) is type(value)
    return restored


def test_decision_acceptance_context_full_typed_round_trip():
    restored = assert_round_trip(
        context(),
        serialize_decision_acceptance_context,
        deserialize_decision_acceptance_context,
    )

    assert type(restored.recommendation) is Recommendation
    assert type(restored.recommendation.opportunity) is Opportunity
    assert type(restored.recommendation.opportunity.candidate) is Candidate
    restored_context = restored.night["object_evaluations"]["M31"][
        "decision_context"
    ]
    assert type(restored_context) is DecisionContext
    assert type(restored_context.session) is SessionContext
    assert type(restored_context.equipment.setup) is ImagingSetup
    assert type(restored.night["selected_window"]) is tuple
    assert type(restored.availability) is SessionAvailability


@pytest.mark.parametrize(
    "source",
    tuple(UserSelectionSource),
)
def test_user_selection_sources_round_trip(source):
    restored = assert_round_trip(
        selection(source),
        serialize_user_selection,
        deserialize_user_selection,
    )

    assert type(restored.source) is UserSelectionSource
    if source is UserSelectionSource.DECLINED:
        assert restored.selected_catalog_key is None


def test_complete_night_mission_typed_round_trip():
    restored = assert_round_trip(
        mission(),
        serialize_night_mission,
        deserialize_night_mission,
    )

    assert type(restored.risk_report) is RiskReport
    assert type(restored.season_analysis) is AnalysisResult
    assert type(restored.productivity) is NightProductivityResult
    assert type(restored.productivity.timeline) is NightTimeline
    assert type(restored.productivity.timeline.slices[0]) is NightSlice
    assert type(restored.astro_quality) is AstroQualityResult
    assert type(restored.dew_risk) is DewRiskResult
    assert type(restored.tasks[0]) is NightTask
    assert type(restored.selected_filter) is SelectedFilter


def test_store_creates_and_reloads_exact_context_after_reconstruction(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    source = context()

    store.create_context(source)
    restored = FileDecisionAcceptanceLineageStore(tmp_path).load_context(
        "decision-1"
    )

    assert restored == source
    assert type(restored.recommendation.opportunity) is Opportunity


def test_identical_context_replay_is_idempotent(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    source = context()
    store.create_context(source)
    before = (tmp_path / "decision-1.json").read_bytes()

    store.create_context(deepcopy(source))

    assert (tmp_path / "decision-1.json").read_bytes() == before


def test_conflicting_context_does_not_overwrite_existing(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    conflicting = context()
    conflicting.profile["active_equipment"] = "different"
    before = (tmp_path / "decision-1.json").read_bytes()

    with pytest.raises(AcceptanceLineageConflictError):
        store.create_context(conflicting)

    assert (tmp_path / "decision-1.json").read_bytes() == before


def test_selection_and_mission_commit_atomically_and_reload_after_reconstruction(
    tmp_path,
):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())

    store.commit_selection_and_mission(selection(), mission())
    reconstructed = FileDecisionAcceptanceLineageStore(tmp_path)

    assert reconstructed.load_selection("selection-1") == selection()
    assert reconstructed.load_mission("mission-1") == mission()


def test_declined_selection_commits_without_fabricated_mission(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    declined = selection(UserSelectionSource.DECLINED)

    store.commit_selection_and_mission(declined, None)

    assert store.load_selection(declined.selection_id) == declined
    with pytest.raises(AcceptanceLineageNotFoundError):
        store.load_mission("mission-1")


def test_exact_selection_and_mission_replay_is_idempotent(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    store.commit_selection_and_mission(selection(), mission())
    before = (tmp_path / "decision-1.json").read_bytes()

    store.commit_selection_and_mission(selection(), mission())

    assert (tmp_path / "decision-1.json").read_bytes() == before


@pytest.mark.parametrize("conflict_kind", ["selection", "mission"])
def test_conflicting_duplicate_identity_fails_closed(tmp_path, conflict_kind):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    store.commit_selection_and_mission(selection(), mission())
    before = (tmp_path / "decision-1.json").read_bytes()
    proposed_selection = selection()
    proposed_mission = mission()
    if conflict_kind == "selection":
        proposed_selection = UserSelection(
            selection_id="selection-1",
            decision_id="decision-1",
            selected_catalog_key="M42",
            source=UserSelectionSource.ALTERNATIVE,
            selected_at=START,
        )
    else:
        proposed_selection = selection(selection_id="selection-2")
        proposed_mission = mission(
            selection_id="selection-2",
        )

    with pytest.raises(AcceptanceLineageConflictError):
        store.commit_selection_and_mission(
            proposed_selection,
            proposed_mission,
        )

    assert (tmp_path / "decision-1.json").read_bytes() == before


@pytest.mark.parametrize(
    "source_selection,source_mission",
    [
        (
            selection(decision_id="decision-2"),
            mission(decision_id="decision-2"),
        ),
        (selection(), mission(decision_id="decision-2")),
        (selection(), mission(selection_id="selection-other")),
    ],
)
def test_cross_decision_or_selection_links_fail_closed(
    tmp_path,
    source_selection,
    source_mission,
):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())

    with pytest.raises(
        (AcceptanceLineageConflictError, AcceptanceLineageNotFoundError)
    ):
        store.commit_selection_and_mission(source_selection, source_mission)


@pytest.mark.parametrize("duplicate_kind", ["selection", "mission"])
def test_duplicate_identity_in_another_aggregate_fails_globally(
    tmp_path,
    duplicate_kind,
):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context("decision-1"))
    store.create_context(context("decision-2"))
    store.commit_selection_and_mission(selection(), mission())
    second_selection_id = (
        "selection-1" if duplicate_kind == "selection" else "selection-2"
    )
    second_mission_id = "mission-2" if duplicate_kind == "selection" else "mission-1"

    with pytest.raises(AcceptanceLineageConflictError):
        store.commit_selection_and_mission(
            selection(
                selection_id=second_selection_id,
                decision_id="decision-2",
            ),
            mission(
                mission_id=second_mission_id,
                decision_id="decision-2",
                selection_id=second_selection_id,
            ),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.update(schema_version=2),
        lambda document: document.pop("schema_version"),
        lambda document: document["context"].update(
            {"$type": "unsupported.DomainType"}
        ),
    ],
)
def test_schema_and_malformed_typed_content_fail_closed(tmp_path, mutate):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    path = tmp_path / "decision-1.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(AcceptanceLineageCorruptionError):
        store.load_context("decision-1")


@pytest.mark.parametrize("decision_id", ["../escape", "nested/path", ".hidden", ""])
def test_decision_id_cannot_escape_lineage_directory(tmp_path, decision_id):
    store = FileDecisionAcceptanceLineageStore(tmp_path)

    with pytest.raises(AcceptanceLineageCorruptionError, match="invalid_decision_id"):
        store.load_context(decision_id)


@pytest.mark.parametrize("malformation", ["enum", "datetime", "missing_field"])
def test_malformed_selection_typed_values_fail_closed(malformation):
    document = serialize_user_selection(selection())
    fields = document["fields"]
    if malformation == "enum":
        fields["source"]["value"] = "unsupported"
    elif malformation == "datetime":
        fields["selected_at"]["value"] = "not-a-datetime"
    else:
        fields.pop("decision_id")

    with pytest.raises(AcceptanceLineageCorruptionError):
        deserialize_user_selection(document)


def test_corrupt_json_fails_closed_and_is_not_skipped_during_scan(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    (tmp_path / "corrupt.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(AcceptanceLineageCorruptionError):
        store.load_selection("unknown-selection")


def test_atomic_replace_failure_preserves_previous_complete_aggregate(
    tmp_path,
    monkeypatch,
):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    path = tmp_path / "decision-1.json"
    before = path.read_bytes()
    monkeypatch.setattr(
        store_module.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        store.commit_selection_and_mission(selection(), mission())

    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".decision-1.*.tmp"))


def test_concurrent_conflicting_commits_allow_exactly_one_success(tmp_path):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    store.create_context(context())
    barrier = Barrier(2)

    def commit(target):
        barrier.wait()
        try:
            store.commit_selection_and_mission(
                selection(
                    UserSelectionSource.PRIMARY_RECOMMENDATION
                    if target == "M31"
                    else UserSelectionSource.ALTERNATIVE
                ),
                mission(),
            )
            return "saved"
        except AcceptanceLineageConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(commit, ("M31", "M42")))

    assert sorted(outcomes) == ["conflict", "saved"]
    assert json.loads((tmp_path / "decision-1.json").read_text())["schema_version"] == 1


def test_unique_temporary_files_are_cleaned(tmp_path, monkeypatch):
    store = FileDecisionAcceptanceLineageStore(tmp_path)
    replaced = []
    original_replace = store_module.os.replace

    def observe_replace(source, destination):
        replaced.append(source.name)
        return original_replace(source, destination)

    monkeypatch.setattr(store_module.os, "replace", observe_replace)
    store.create_context(context("decision-1"))
    store.create_context(context("decision-2"))

    assert len(set(replaced)) == 2
    assert all(name.startswith(".decision-") for name in replaced)
    assert not list(tmp_path.glob(".*.tmp"))
