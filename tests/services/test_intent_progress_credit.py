from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from types import SimpleNamespace

import pytest

from astropilot.execution_lineage_store import FileExecutionLineageStore
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence, OutcomeEvidenceCategory, OutcomeEvidenceSource,
)
from decision.services.acquisition_intent_remaining_progress import derive_acquisition_intent_remaining_progress
from decision.services.intent_progress_credit import (
    IntentProgressCreditError, apply_execution_credit, credit_totals,
    validate_credit_authority,
)
from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
from decision.models.project_acquisition_intent_target import ProjectAcquisitionIntentTarget


START = datetime(2026, 9, 21, 20, tzinfo=timezone.utc)
FIELD = "sh2-129_ou4"
INTENT = "ou4_oiii"


@pytest.fixture
def context(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    source = Execution("execution-1", "mission-1", ExecutionStatus.NOT_STARTED, None, None, None)
    store.create_execution(source)
    mission = SimpleNamespace(mission_id="mission-1", decision_id="decision-1",
                              selection_id="selection-1", imaging_field_id=FIELD,
                              acquisition_intent_id=INTENT, target="Sh2-129")
    selection = SimpleNamespace(selection_id="selection-1", decision_id="decision-1",
                                selected_catalog_key="Sh2-129", selected_imaging_field_id=FIELD,
                                selected_acquisition_intent_id=INTENT)
    profile = {"profile_revision": 0, "projects": {"Sh2-129": {
        "hours": 2, "target_hours": 20, "imaging_field_id": FIELD,
    }}, "portfolio_credit_applications": {"old-credit": {"unchanged": True}}}
    write_lock = Lock()

    def save(candidate, *, expected_revision):
        with write_lock:
            if expected_revision != profile["profile_revision"]:
                raise IntentProgressCreditError("profile_revision_conflict")
            validate_credit_authority(candidate, profile)
            profile.clear()
            profile.update(deepcopy(candidate))
            profile["profile_revision"] += 1
            return profile

    def apply(*, ids=("evidence-1",), confirm=False, revision=None, execution_id="execution-1"):
        return apply_execution_credit(
            profile=deepcopy(profile), execution_id=execution_id, evidence_ids=ids,
            expected_revision=profile["profile_revision"] if revision is None else revision,
            confirm_historical_baseline=confirm,
            load_execution=store.load_execution, load_mission=lambda _: mission,
            load_selection=lambda _: selection, load_evidence=store.load_evidence,
            save_profile=save,
        )

    def close(status=ExecutionStatus.COMPLETED):
        store.replace_execution(Execution("execution-1", "mission-1", status,
            START, START + timedelta(hours=3), timedelta(hours=3)), expected_execution=source)

    def evidence(evidence_id="evidence-1", duration=timedelta(minutes=30, microseconds=37),
                 execution_id="execution-1"):
        item = AcquisitionOutcomeEvidence(evidence_id, execution_id,
            OutcomeEvidenceCategory.ACQUISITION, START, OutcomeEvidenceSource.USER,
            actual_capture_duration=timedelta(hours=2), usable_integration_duration=duration)
        store.append_evidence(item)

    return SimpleNamespace(store=store, profile=profile, mission=mission,
                           selection=selection, apply=apply, close=close, evidence=evidence)


def test_persisted_execution_multiple_observations_replay_and_projection(context):
    context.close()
    context.evidence()
    context.evidence("evidence-2", timedelta(seconds=1, microseconds=9))
    status, entry, revision = context.apply(ids=("evidence-2", "evidence-1"))
    assert status == "applied" and revision == 1
    assert entry["total_duration_us"] == 1_801_000_046
    assert entry["evidence_ids"] == ["evidence-1", "evidence-2"]
    assert entry["mission_id"] == "mission-1" and entry["selection_id"] == "selection-1"
    assert entry["decision_id"] == "decision-1"
    assert context.store.load_execution("execution-1").status is ExecutionStatus.COMPLETED
    assert context.profile["projects"]["Sh2-129"]["hours"] == 2
    assert context.profile["projects"]["Sh2-129"]["target_hours"] == 20
    assert context.profile["portfolio_credit_applications"] == {"old-credit": {"unchanged": True}}
    assert context.apply(ids=("evidence-1", "evidence-2")) == ("already_applied", entry, 1)
    field = build_production_imaging_field_resolver().resolve(FIELD)
    derived = derive_acquisition_intent_remaining_progress(field,
        (ProjectAcquisitionIntentTarget(INTENT, 1),), (), credit_totals(context.profile, "Sh2-129"))
    assert next(item for item in derived if item.acquisition_intent_id == INTENT).acquired_seconds == 1801.000046
    assert next(item for item in derived if item.acquisition_intent_id != INTENT).acquired_seconds is None
    assert "acquisition_intent_progress" not in context.profile["projects"]["Sh2-129"]


@pytest.mark.parametrize("status", [ExecutionStatus.INTERRUPTED, ExecutionStatus.UNCONFIRMED, ExecutionStatus.NOT_STARTED])
def test_ineligible_execution_states(context, status):
    if status is not ExecutionStatus.NOT_STARTED and status is not ExecutionStatus.UNCONFIRMED:
        context.close(status)
    elif status is ExecutionStatus.UNCONFIRMED:
        context.store.replace_execution(Execution("execution-1", "mission-1", status, None, None, None),
                                         expected_execution=context.store.load_execution("execution-1"))
    context.evidence()
    with pytest.raises(IntentProgressCreditError, match="execution_not_completed"):
        context.apply()


@pytest.mark.parametrize("duration", [None, timedelta(0)])
def test_unknown_or_zero_usable_duration_never_falls_back_to_actual(context, duration):
    context.close()
    context.evidence(duration=duration)
    with pytest.raises(IntentProgressCreditError, match="evidence_ineligible|usable_duration_required"):
        context.apply()


def test_missing_foreign_and_late_evidence(context):
    context.close()
    with pytest.raises(Exception, match="evidence_not_found"):
        context.apply()
    context.evidence()
    context.apply()
    context.evidence("late")
    assert context.apply()[0] == "already_applied"
    with pytest.raises(IntentProgressCreditError, match="execution_credit_conflict"):
        context.apply(ids=("evidence-1", "not-yet-recorded"))
    with pytest.raises(IntentProgressCreditError, match="execution_credit_conflict"):
        context.apply(ids=("evidence-1", "late"))
    assert len(context.profile["intent_progress_credits"]) == 1


def test_foreign_evidence_never_credits_even_if_usable(context):
    context.close()
    context.store.create_execution(Execution("execution-2", "mission-1",
        ExecutionStatus.NOT_STARTED, None, None, None))
    context.evidence("foreign", execution_id="execution-2")
    with pytest.raises(IntentProgressCreditError, match="evidence_ineligible"):
        context.apply(ids=("foreign",))
    assert "intent_progress_credits" not in context.profile


@pytest.mark.parametrize("base", [None, 0, 3600])
def test_baseline_confirmation_and_immutable_base(context, base):
    if base is not None:
        context.profile["projects"]["Sh2-129"]["acquisition_intent_progress"] = [
            {"acquisition_intent_id": INTENT, "acquired_duration_manual": base}]
    context.close()
    context.evidence()
    if base:
        with pytest.raises(IntentProgressCreditError, match="baseline_confirmation_required"):
            context.apply()
    context.apply(confirm=bool(base))
    candidate = deepcopy(context.profile)
    candidate["projects"]["Sh2-129"]["acquisition_intent_progress"] = (
        [{"acquisition_intent_id": INTENT, "acquired_duration_manual": 42}]
        if base is None else []
    )
    with pytest.raises(IntentProgressCreditError, match="baseline|base_locked"):
        validate_credit_authority(candidate, context.profile)
    changed = deepcopy(context.profile)
    changed["projects"]["Sh2-129"]["imaging_field_id"] = "unknown"
    with pytest.raises(IntentProgressCreditError, match="ledger_invalid"):
        validate_credit_authority(changed, context.profile)


@pytest.mark.parametrize("repeat_confirmation", [False, True])
def test_confirmed_baseline_is_reused_for_distinct_execution_credits(context, repeat_confirmation):
    context.profile["projects"]["Sh2-129"]["acquisition_intent_progress"] = [
        {"acquisition_intent_id": INTENT, "acquired_duration_manual": 3600}]
    context.close()
    context.evidence()
    first = context.apply(confirm=True)[1]
    marker = deepcopy(context.profile["intent_progress_baselines"]["Sh2-129"][INTENT])

    source = Execution("execution-2", "mission-1", ExecutionStatus.NOT_STARTED, None, None, None)
    context.store.create_execution(source)
    context.store.replace_execution(Execution("execution-2", "mission-1", ExecutionStatus.COMPLETED,
        START, START + timedelta(hours=3), timedelta(hours=3)), expected_execution=source)
    context.evidence("evidence-2", timedelta(minutes=15), execution_id="execution-2")
    second = context.apply(ids=("evidence-2",), execution_id="execution-2",
                           confirm=repeat_confirmation)
    assert second[0] == "applied" and second[1]["execution_id"] == "execution-2"
    assert context.profile["intent_progress_baselines"]["Sh2-129"][INTENT] == marker
    assert context.apply(ids=("evidence-2",), execution_id="execution-2", confirm=True)[0] == "already_applied"
    assert context.apply()[0] == "already_applied"
    assert context.profile["intent_progress_baselines"]["Sh2-129"][INTENT] == marker
    assert len(context.profile["intent_progress_credits"]) == 2
    assert credit_totals(context.profile, "Sh2-129")[INTENT] == first["total_duration_us"] + second[1]["total_duration_us"]
    field = build_production_imaging_field_resolver().resolve(FIELD)
    derived = derive_acquisition_intent_remaining_progress(field,
        (ProjectAcquisitionIntentTarget(INTENT, 2),),
        tuple(context.profile["projects"]["Sh2-129"]["acquisition_intent_progress"]),
        credit_totals(context.profile, "Sh2-129"))
    progress = next(item for item in derived if item.acquisition_intent_id == INTENT)
    assert progress.acquired_seconds == 6300.000037
    assert progress.remaining_hours == pytest.approx(0.24999998972222226)
    assert context.profile["projects"]["Sh2-129"]["hours"] == 2
    assert context.profile["projects"]["Sh2-129"]["target_hours"] == 20


def test_stale_revision_and_corrupt_or_replaced_ledger(context):
    context.close()
    context.evidence()
    context.apply()
    with pytest.raises(IntentProgressCreditError, match="revision_conflict"):
        context.apply(revision=0)
    candidate = deepcopy(context.profile)
    candidate["intent_progress_credits"]["execution-1"]["total_duration_us"] += 1
    with pytest.raises(IntentProgressCreditError, match="ledger_invalid"):
        validate_credit_authority(candidate)
    candidate = deepcopy(context.profile)
    candidate["intent_progress_credits"].clear()
    with pytest.raises(IntentProgressCreditError, match="immutable"):
        validate_credit_authority(candidate, context.profile)


def test_concurrent_same_revision_awards_at_most_one_credit(context):
    context.close()
    context.evidence()
    def attempt(_):
        try:
            return context.apply(revision=0)[0]
        except IntentProgressCreditError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(outcomes) == ["applied", "profile_revision_conflict"]
    assert context.profile["profile_revision"] == 1
    assert len(context.profile["intent_progress_credits"]) == 1


def test_provenance_and_project_mismatches(context):
    context.close()
    context.evidence()
    context.selection.selected_acquisition_intent_id = "other"
    with pytest.raises(IntentProgressCreditError, match="mission_provenance_invalid"):
        context.apply()
    context.selection.selected_acquisition_intent_id = INTENT
    context.mission.acquisition_intent_id = "other"
    context.selection.selected_acquisition_intent_id = "other"
    with pytest.raises(IntentProgressCreditError, match="intent_unknown"):
        context.apply()
    context.mission.acquisition_intent_id = INTENT
    context.selection.selected_acquisition_intent_id = INTENT
    context.profile["projects"]["Sh2-129"]["imaging_field_id"] = "ic1396"
    with pytest.raises(IntentProgressCreditError, match="project_field_mismatch"):
        context.apply()
