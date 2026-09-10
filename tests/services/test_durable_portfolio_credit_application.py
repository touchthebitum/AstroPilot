import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

import astropilot.user_profile as user_profile
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
)
from decision.models.portfolio_credit import PortfolioCredit
from decision.models.portfolio_credit_application import (
    PortfolioCreditApplication,
    PortfolioCreditApplicationOutcome,
    PortfolioCreditDestinationKind,
)
from decision.services.durable_portfolio_credit_application import (
    DurablePortfolioCreditApplicationService,
)


START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
END = datetime(2026, 9, 10, 23, 12, tzinfo=timezone.utc)
DURATION = timedelta(hours=1, minutes=12)
APPLIED_AT = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)


def execution(status=ExecutionStatus.INTERRUPTED):
    if status in (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED):
        return Execution("execution-1", "mission-1", status, START, END, DURATION)
    if status is ExecutionStatus.IN_PROGRESS:
        return Execution("execution-1", "mission-1", status, START, None, None)
    return Execution("execution-1", "mission-1", status, None, None, None)


def evidence(usable=DURATION):
    return AcquisitionOutcomeEvidence(
        evidence_id="evidence-1",
        execution_id="execution-1",
        category=OutcomeEvidenceCategory.ACQUISITION,
        observed_at=END,
        source=OutcomeEvidenceSource.USER,
        actual_capture_duration=timedelta(hours=3),
        usable_integration_duration=usable,
    )


def credit(credit_id="credit-1", usable=DURATION):
    return PortfolioCredit(
        credit_id=credit_id,
        execution_id="execution-1",
        evidence_ids=("evidence-1",),
        usable_integration_duration=usable,
        credited_at=END,
    )


def application(credit_id="credit-1", duration=DURATION, object_name="M31"):
    return PortfolioCreditApplication(
        application_id=f"application-{credit_id}",
        credit_id=credit_id,
        object_name=object_name,
        destination_kind=PortfolioCreditDestinationKind.PROJECT,
        applied_duration=duration,
        applied_at=APPLIED_AT,
    )


def write_profile(path):
    path.write_text(json.dumps({
        "projects": {
            "M31": {"hours": 2.0, "target_hours": 20.0, "importance": 8},
            "M42": {"hours": 4.0, "target_hours": 20.0, "importance": 6},
        },
        "sessions": [],
    }), encoding="utf-8")


def service(profile_path, *, status=ExecutionStatus.INTERRUPTED, saver=None):
    source_execution = execution(status)
    source_evidence = evidence()

    def load_profile():
        return json.loads(profile_path.read_text(encoding="utf-8"))

    def save_profile(profile):
        profile_path.write_text(json.dumps(profile), encoding="utf-8")

    return (
        DurablePortfolioCreditApplicationService(
            load_profile=load_profile,
            save_profile=saver or save_profile,
            execution_loader=lambda execution_id: (
                source_execution if execution_id == "execution-1" else None
            ),
            evidence_loader=lambda evidence_id: (
                source_evidence if evidence_id == "evidence-1" else None
            ),
        ),
        source_execution,
        source_evidence,
    )


@pytest.mark.parametrize("status", [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED])
def test_closed_execution_credit_is_durable_and_uses_only_usable_duration(tmp_path, status):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    application_service, source_execution, source_evidence = service(
        profile_path,
        status=status,
    )
    before_execution = asdict(source_execution)
    before_evidence = asdict(source_evidence)

    result = application_service.apply(application(), credit())
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert result.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert persisted["projects"]["M31"]["hours"] == 3.2
    assert persisted["projects"]["M42"]["hours"] == 4.0
    assert persisted["projects"]["M31"]["importance"] == 8
    assert persisted["projects"]["M31"]["hours"] != 2.0 + 3.0
    assert persisted["portfolio_credit_applications"]["credit-1"]["credit_id"] == "credit-1"
    assert asdict(source_execution) == before_execution
    assert asdict(source_evidence) == before_evidence


def test_same_credit_replay_after_fresh_service_reload_is_not_applied_twice(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    first, _, _ = service(profile_path)
    first_result = first.apply(application(), credit())

    def unavailable(_identity):
        pytest.fail("durable replay must resolve from persisted credit_id")

    reloaded = DurablePortfolioCreditApplicationService(
        load_profile=lambda: json.loads(profile_path.read_text(encoding="utf-8")),
        save_profile=lambda profile: pytest.fail("replay must not rewrite state"),
        execution_loader=unavailable,
        evidence_loader=unavailable,
    )
    replay = reloaded.apply(application(), credit())
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert first_result.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert replay.outcome is PortfolioCreditApplicationOutcome.ALREADY_APPLIED
    assert replay.application == first_result.application
    assert persisted["projects"]["M31"]["hours"] == 3.2


def test_same_service_replay_and_distinct_credit_ids_have_canonical_semantics(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    application_service, _, _ = service(profile_path)

    first = application_service.apply(application(), credit())
    replay = application_service.apply(application(), credit())
    second = application_service.apply(
        application("credit-2"),
        credit("credit-2"),
    )
    persisted = json.loads(profile_path.read_text(encoding="utf-8"))

    assert first.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert replay.outcome is PortfolioCreditApplicationOutcome.ALREADY_APPLIED
    assert second.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert persisted["projects"]["M31"]["hours"] == 4.4
    assert set(persisted["portfolio_credit_applications"]) == {"credit-1", "credit-2"}


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.NOT_STARTED, ExecutionStatus.IN_PROGRESS, ExecutionStatus.UNCONFIRMED],
)
def test_ineligible_execution_never_reaches_persistence(tmp_path, status):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    before = profile_path.read_bytes()
    application_service, _, _ = service(profile_path, status=status)

    with pytest.raises(ValueError, match="execution_status_ineligible"):
        application_service.apply(application(), credit())

    assert profile_path.read_bytes() == before


def test_zero_credit_is_recorded_without_progress_change(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    source_evidence = evidence(timedelta(0))
    application_service = DurablePortfolioCreditApplicationService(
        load_profile=lambda: json.loads(profile_path.read_text(encoding="utf-8")),
        save_profile=lambda profile: profile_path.write_text(json.dumps(profile)),
        execution_loader=lambda _: execution(),
        evidence_loader=lambda _: source_evidence,
    )

    result = application_service.apply(
        application(duration=timedelta(0)),
        credit(usable=timedelta(0)),
    )
    persisted = json.loads(profile_path.read_text())

    assert result.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert persisted["projects"]["M31"]["hours"] == 2.0
    assert "credit-1" in persisted["portfolio_credit_applications"]


def test_unresolved_project_and_save_failure_leave_persisted_state_unchanged(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    before = profile_path.read_bytes()
    application_service, _, _ = service(profile_path)

    with pytest.raises(ValueError, match="project_destination_unresolved"):
        application_service.apply(application(object_name="NGC7000"), credit())
    assert profile_path.read_bytes() == before

    failing, _, _ = service(
        profile_path,
        saver=lambda profile: (_ for _ in ()).throw(OSError("save failed")),
    )
    with pytest.raises(OSError, match="save failed"):
        failing.apply(application(), credit())
    assert profile_path.read_bytes() == before


def test_target_destination_records_credit_without_fabricating_project(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    application_service, _, _ = service(profile_path)
    target_application = PortfolioCreditApplication(
        application_id="application-1",
        credit_id="credit-1",
        object_name="NGC7000",
        destination_kind=PortfolioCreditDestinationKind.TARGET,
        applied_duration=DURATION,
        applied_at=APPLIED_AT,
    )

    application_service.apply(target_application, credit())
    persisted = json.loads(profile_path.read_text())

    assert "NGC7000" not in persisted["projects"]
    assert persisted["projects"]["M31"]["hours"] == 2.0
    assert "credit-1" in persisted["portfolio_credit_applications"]


@pytest.mark.parametrize("ledger", [None, [], "invalid", 1, True])
def test_malformed_ledger_top_level_fails_closed(tmp_path, ledger):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    profile = json.loads(profile_path.read_text())
    profile["portfolio_credit_applications"] = ledger
    profile_path.write_text(json.dumps(profile))
    application_service, _, _ = service(profile_path)

    with pytest.raises(ValueError, match="portfolio_credit_ledger_inconsistent"):
        application_service.apply(application(), credit())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda entry: entry.pop("application_id"),
        lambda entry: entry.update(application_id=""),
        lambda entry: entry.update(applied_duration_us="4320000000"),
        lambda entry: entry.update(applied_at="2026-09-11T01:00:00"),
        lambda entry: entry["credit"].pop("execution_id"),
        lambda entry: entry["credit"].update(evidence_ids="evidence-1"),
        lambda entry: entry["credit"].update(credited_at="not-a-time"),
    ],
)
def test_malformed_or_partial_ledger_entry_fails_closed(tmp_path, mutation):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    application_service, _, _ = service(profile_path)
    application_service.apply(application(), credit())
    profile = json.loads(profile_path.read_text())
    mutation(profile["portfolio_credit_applications"]["credit-1"])
    profile_path.write_text(json.dumps(profile))

    with pytest.raises(ValueError, match="portfolio_credit_ledger_inconsistent"):
        application_service.apply(application(), credit())


def test_ledger_key_credit_id_and_duration_mismatches_fail_closed(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    application_service, _, _ = service(profile_path)
    application_service.apply(application(), credit())
    canonical = json.loads(profile_path.read_text())

    for mutate in (
        lambda ledger: ledger.update(
            {"wrong-credit": ledger.pop("credit-1")}
        ),
        lambda ledger: ledger["credit-1"].update(credit_id="wrong-credit"),
        lambda ledger: ledger["credit-1"].update(applied_duration_us=1),
    ):
        profile = json.loads(json.dumps(canonical))
        mutate(profile["portfolio_credit_applications"])
        profile_path.write_text(json.dumps(profile))
        with pytest.raises(ValueError, match="portfolio_credit_ledger_inconsistent"):
            application_service.apply(application(), credit())


def test_persisted_project_destination_must_still_resolve(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    application_service, _, _ = service(profile_path)
    application_service.apply(application(), credit())
    profile = json.loads(profile_path.read_text())
    profile["portfolio_credit_applications"]["credit-1"][
        "object_name"
    ] = "missing-project"
    profile_path.write_text(json.dumps(profile))

    with pytest.raises(ValueError, match="portfolio_credit_ledger_inconsistent"):
        application_service.apply(application(), credit())


def test_project_capacity_overflow_fails_before_save_and_leaves_profile_unchanged(tmp_path):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    profile = json.loads(profile_path.read_text())
    profile["projects"]["M31"]["hours"] = 19.5
    profile_path.write_text(json.dumps(profile))
    before = profile_path.read_bytes()
    saves = []
    application_service, _, _ = service(
        profile_path,
        saver=lambda profile: saves.append(profile),
    )

    with pytest.raises(ValueError, match="project_capacity_exceeded"):
        application_service.apply(application(), credit())

    assert saves == []
    assert profile_path.read_bytes() == before


def valid_profile_document():
    return {
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
        "projects": {
            "M31": {
                "hours": 2.0,
                "target_hours": 20.0,
                "importance": 8,
            }
        },
        "sessions": [],
    }


def test_real_profile_load_save_round_trip_preserves_ledger_and_progress(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(json.dumps(valid_profile_document()))
    application_service = DurablePortfolioCreditApplicationService(
        load_profile=user_profile.load_user_profile,
        save_profile=user_profile.save_user_profile,
        execution_loader=lambda _: execution(),
        evidence_loader=lambda _: evidence(),
    )

    application_service.apply(application(), credit())
    reloaded = user_profile.load_user_profile()

    assert reloaded["projects"]["M31"]["hours"] == 3.2
    assert reloaded["portfolio_credit_applications"]["credit-1"][
        "application_id"
    ] == "application-credit-1"


def test_real_atomic_writer_failure_preserves_previous_complete_profile(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(json.dumps(valid_profile_document()))
    before = profile_path.read_bytes()
    application_service = DurablePortfolioCreditApplicationService(
        load_profile=user_profile.load_user_profile,
        save_profile=user_profile.save_user_profile,
        execution_loader=lambda _: execution(),
        evidence_loader=lambda _: evidence(),
    )

    def fail_replace(path, target):
        raise OSError("replace failed")

    monkeypatch.setattr(user_profile.Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        application_service.apply(application(), credit())

    assert profile_path.read_bytes() == before
