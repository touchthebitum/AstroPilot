"""Validated, append-only execution credits, separate from manual progress."""

from datetime import datetime, timedelta, timezone
from collections.abc import Mapping

from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
from decision.models.execution import ExecutionStatus
from decision.models.outcome_evidence import AcquisitionOutcomeEvidence
from decision.services.imaging_field_resolver import ImagingFieldResolutionError
from decision.services.project_acquisition_intent_progress import (
    resolve_project_acquisition_intent_progress, calculated_duration_seconds,
)


class IntentProgressCreditError(ValueError):
    pass


FIELDS = frozenset({
    "execution_id", "mission_id", "decision_id", "selection_id", "project_id",
    "imaging_field_id", "acquisition_intent_id", "evidence_ids",
    "usable_durations_us", "total_duration_us", "applied_at",
})


def duration_us(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def base_seconds(entry):
    if entry is None:
        return None
    if "acquired_duration_manual" in entry:
        return float(entry["acquired_duration_manual"])
    return calculated_duration_seconds(entry["acquired_frames"], entry["exposure_seconds"])


def load_credits(profile: Mapping) -> dict:
    ledger = profile.get("intent_progress_credits", {})
    if type(ledger) is not dict:
        raise IntentProgressCreditError("intent_progress_ledger_invalid")
    projects = profile.get("projects", {})
    if type(projects) is not dict:
        raise IntentProgressCreditError("intent_progress_ledger_invalid")
    resolver = build_production_imaging_field_resolver()
    seen_evidence = set()
    for execution_id, entry in ledger.items():
        if type(execution_id) is not str or not execution_id or type(entry) is not dict or set(entry) != FIELDS:
            raise IntentProgressCreditError("intent_progress_ledger_invalid")
        for name in ("execution_id", "mission_id", "decision_id", "selection_id", "project_id", "imaging_field_id", "acquisition_intent_id"):
            if type(entry[name]) is not str or not entry[name].strip():
                raise IntentProgressCreditError("intent_progress_ledger_invalid")
        ids, durations = entry["evidence_ids"], entry["usable_durations_us"]
        if (entry["execution_id"] != execution_id or type(ids) is not list or not ids
            or any(type(i) is not str or not i for i in ids) or len(set(ids)) != len(ids)
            or ids != sorted(ids) or type(durations) is not list or len(ids) != len(durations)
            or any(type(d) is not int or d <= 0 for d in durations)
            or type(entry["total_duration_us"]) is not int
            or entry["total_duration_us"] != sum(durations)):
            raise IntentProgressCreditError("intent_progress_ledger_invalid")
        if seen_evidence.intersection(ids):
            raise IntentProgressCreditError("intent_progress_ledger_invalid")
        seen_evidence.update(ids)
        try:
            applied = datetime.fromisoformat(entry["applied_at"])
        except (TypeError, ValueError):
            raise IntentProgressCreditError("intent_progress_ledger_invalid") from None
        if applied.tzinfo is None or applied.utcoffset() is None:
            raise IntentProgressCreditError("intent_progress_ledger_invalid")
        project = projects.get(entry["project_id"])
        if type(project) is not dict or project.get("imaging_field_id") != entry["imaging_field_id"]:
            raise IntentProgressCreditError("intent_progress_ledger_invalid")
        try:
            field = resolver.resolve(entry["imaging_field_id"])
        except (AttributeError, ValueError, KeyError):
            raise IntentProgressCreditError("intent_progress_ledger_invalid") from None
        if field is None or entry["acquisition_intent_id"] not in {i.acquisition_intent_id for i in field.acquisition_intents}:
            raise IntentProgressCreditError("intent_progress_ledger_invalid")
    return ledger


def validate_credit_authority(profile: Mapping, previous: Mapping | None = None) -> None:
    ledger = load_credits(profile)
    markers = profile.get("intent_progress_baselines", {})
    if type(markers) is not dict:
        raise IntentProgressCreditError("intent_progress_baseline_invalid")
    for project_id, intents in markers.items():
        if type(intents) is not dict or project_id not in profile["projects"]:
            raise IntentProgressCreditError("intent_progress_baseline_invalid")
        project = profile["projects"][project_id]
        entries = {e["acquisition_intent_id"]: e for e in resolve_project_acquisition_intent_progress(project, build_production_imaging_field_resolver())}
        for intent_id, marker in intents.items():
            if (type(marker) is not dict or set(marker) != {"confirmed_at", "base_progress"}
                or type(marker["base_progress"]) is not dict or marker["base_progress"] != entries.get(intent_id)):
                raise IntentProgressCreditError("intent_progress_baseline_invalid")
            try:
                at = datetime.fromisoformat(marker["confirmed_at"])
            except (TypeError, ValueError):
                raise IntentProgressCreditError("intent_progress_baseline_invalid") from None
            if at.tzinfo is None or at.utcoffset() is None or base_seconds(marker["base_progress"]) is None or base_seconds(marker["base_progress"]) <= 0:
                raise IntentProgressCreditError("intent_progress_baseline_invalid")
    for entry in ledger.values():
        project = profile["projects"][entry["project_id"]]
        entries = {e["acquisition_intent_id"]: e for e in resolve_project_acquisition_intent_progress(project, build_production_imaging_field_resolver())}
        base = base_seconds(entries.get(entry["acquisition_intent_id"]))
        if base is not None and base > 0 and entry["acquisition_intent_id"] not in markers.get(entry["project_id"], {}):
            raise IntentProgressCreditError("intent_progress_baseline_required")
    if previous is not None:
        old_ledger = load_credits(previous)
        if any(ledger.get(key) != value for key, value in old_ledger.items()):
            raise IntentProgressCreditError("intent_progress_credits_immutable")
        old_markers = previous.get("intent_progress_baselines", {})
        if any(markers.get(key, {}).get(intent) != marker for key, intents in old_markers.items() for intent, marker in intents.items()):
            raise IntentProgressCreditError("intent_progress_baseline_immutable")
        credited = {(e["project_id"], e["acquisition_intent_id"]) for e in old_ledger.values()}
        for project_id, intent_id in credited:
            old_project, new_project = previous["projects"][project_id], profile["projects"].get(project_id)
            if new_project is None or old_project.get("imaging_field_id") != new_project.get("imaging_field_id"):
                raise IntentProgressCreditError("intent_progress_field_locked")
            def source(project):
                return next((e for e in project.get("acquisition_intent_progress", ()) if e["acquisition_intent_id"] == intent_id), None)
            if source(old_project) != source(new_project):
                raise IntentProgressCreditError("intent_progress_base_locked")


def credit_totals(profile: Mapping, project_id: str) -> dict[str, int]:
    totals = {}
    for entry in load_credits(profile).values():
        if entry["project_id"] == project_id:
            key = entry["acquisition_intent_id"]
            totals[key] = totals.get(key, 0) + entry["total_duration_us"]
    return totals


def apply_execution_credit(*, profile, execution_id, evidence_ids, expected_revision,
                           confirm_historical_baseline, load_execution, load_mission,
                           load_selection, load_evidence, save_profile):
    ledger = load_credits(profile)
    validate_credit_authority(profile)
    if expected_revision != profile.get("profile_revision", 0):
        raise IntentProgressCreditError("profile_revision_conflict")
    if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
        raise IntentProgressCreditError("evidence_ids_invalid")
    prior = ledger.get(execution_id)
    if prior is not None and sorted(evidence_ids) != prior["evidence_ids"]:
        raise IntentProgressCreditError("execution_credit_conflict")
    execution = load_execution(execution_id)
    if execution is None:
        raise IntentProgressCreditError("execution_not_found")
    if execution.execution_id != execution_id or execution.status is not ExecutionStatus.COMPLETED:
        raise IntentProgressCreditError("execution_not_completed")
    mission = load_mission(execution.mission_id)
    if mission is None:
        raise IntentProgressCreditError("mission_not_found")
    selection = load_selection(mission.selection_id)
    if selection is None:
        raise IntentProgressCreditError("selection_not_found")
    if (mission.mission_id != execution.mission_id or mission.decision_id != selection.decision_id
        or mission.selection_id != selection.selection_id or mission.imaging_field_id != selection.selected_imaging_field_id
        or mission.acquisition_intent_id is None or mission.acquisition_intent_id != selection.selected_acquisition_intent_id):
        raise IntentProgressCreditError("mission_provenance_invalid")
    project_id = selection.selected_catalog_key
    project = profile.get("projects", {}).get(project_id)
    if project is None or project.get("imaging_field_id") != mission.imaging_field_id:
        raise IntentProgressCreditError("project_field_mismatch")
    try:
        field = build_production_imaging_field_resolver().resolve(mission.imaging_field_id)
    except ImagingFieldResolutionError:
        raise IntentProgressCreditError("intent_unknown") from None
    if mission.acquisition_intent_id not in {i.acquisition_intent_id for i in field.acquisition_intents}:
        raise IntentProgressCreditError("intent_unknown")
    observed = []
    for evidence_id in sorted(evidence_ids):
        evidence = load_evidence(evidence_id)
        if evidence is None:
            raise IntentProgressCreditError("evidence_not_found")
        if (not isinstance(evidence, AcquisitionOutcomeEvidence) or evidence.evidence_id != evidence_id
            or evidence.execution_id != execution_id or evidence.usable_integration_duration is None):
            raise IntentProgressCreditError("evidence_ineligible")
        microseconds = duration_us(evidence.usable_integration_duration)
        if microseconds <= 0:
            raise IntentProgressCreditError("usable_duration_required")
        observed.append(microseconds)
    content = dict(execution_id=execution_id, mission_id=mission.mission_id,
                   decision_id=mission.decision_id, selection_id=mission.selection_id,
                   project_id=project_id, imaging_field_id=mission.imaging_field_id,
                   acquisition_intent_id=mission.acquisition_intent_id,
                   evidence_ids=sorted(evidence_ids), usable_durations_us=observed,
                   total_duration_us=sum(observed))
    existing = ledger.get(execution_id)
    if existing is not None:
        if {k: v for k, v in existing.items() if k != "applied_at"} != content:
            raise IntentProgressCreditError("execution_credit_conflict")
        return "already_applied", existing, profile["profile_revision"]
    entries = {e["acquisition_intent_id"]: e for e in resolve_project_acquisition_intent_progress(project, build_production_imaging_field_resolver())}
    base = entries.get(mission.acquisition_intent_id)
    if base_seconds(base) is not None and base_seconds(base) > 0:
        markers = profile.get("intent_progress_baselines", {}).get(project_id, {})
        if mission.acquisition_intent_id not in markers:
            if not confirm_historical_baseline:
                raise IntentProgressCreditError("intent_progress_baseline_confirmation_required")
            profile.setdefault("intent_progress_baselines", {}).setdefault(project_id, {})[mission.acquisition_intent_id] = {
                "confirmed_at": datetime.now(timezone.utc).isoformat(), "base_progress": dict(base),
            }
    applied_at = datetime.now(timezone.utc)
    # Preserve append chronology even when the clock stalls or moves backwards.
    # Existing ledger entries remain immutable, including their applied_at on replay.
    previous_times = (datetime.fromisoformat(item["applied_at"]) for item in ledger.values()
                      if (item["project_id"], item["acquisition_intent_id"]) ==
                      (project_id, mission.acquisition_intent_id))
    latest = max(previous_times, default=None)
    if latest is not None and applied_at <= latest:
        applied_at = latest + timedelta(microseconds=1)
    entry = {**content, "applied_at": applied_at.isoformat()}
    profile.setdefault("intent_progress_credits", {})[execution_id] = entry
    saved = save_profile(profile, expected_revision=expected_revision)
    return "applied", entry, saved["profile_revision"]
