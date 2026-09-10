from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import datetime, timedelta
import math

from decision.models.execution import Execution
from decision.models.outcome_evidence import OutcomeEvidence
from decision.models.portfolio_credit import PortfolioCredit
from decision.models.portfolio_credit_application import (
    PortfolioCreditApplication,
    PortfolioCreditApplicationOutcome,
    PortfolioCreditApplicationResult,
    PortfolioCreditDestinationKind,
)
from decision.services.portfolio_credit_application import apply_portfolio_credit
from decision.services.portfolio_credit_validation import validate_portfolio_credit


LEDGER_FIELD = "portfolio_credit_applications"
LEDGER_ENTRY_FIELDS = frozenset(
    {
        "application_id",
        "credit_id",
        "object_name",
        "destination_kind",
        "applied_duration_us",
        "applied_at",
        "credit",
    }
)
CREDIT_FIELDS = frozenset(
    {
        "execution_id",
        "evidence_ids",
        "usable_integration_duration_us",
        "credited_at",
    }
)


def _duration_document(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _duration(value: object) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("portfolio_credit_ledger_inconsistent")
    return timedelta(microseconds=value)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("portfolio_credit_ledger_inconsistent")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("portfolio_credit_ledger_inconsistent") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("portfolio_credit_ledger_inconsistent")
    return result


def _ledger_entry(
    application: PortfolioCreditApplication,
    credit: PortfolioCredit,
) -> dict[str, object]:
    return {
        "application_id": application.application_id,
        "credit_id": application.credit_id,
        "object_name": application.object_name,
        "destination_kind": application.destination_kind.value,
        "applied_duration_us": _duration_document(application.applied_duration),
        "applied_at": application.applied_at.isoformat(),
        "credit": {
            "execution_id": credit.execution_id,
            "evidence_ids": list(credit.evidence_ids),
            "usable_integration_duration_us": _duration_document(
                credit.usable_integration_duration
            ),
            "credited_at": credit.credited_at.isoformat(),
        },
    }


def _load_ledger(profile: Mapping) -> tuple[
    dict[str, PortfolioCreditApplication],
    dict[str, PortfolioCredit],
]:
    document = profile.get(LEDGER_FIELD, {})
    if type(document) is not dict:
        raise ValueError("portfolio_credit_ledger_inconsistent")
    applications = {}
    credits = {}
    application_ids = set()
    for credit_id, entry in document.items():
        if (
            not isinstance(credit_id, str)
            or not credit_id.strip()
            or type(entry) is not dict
            or set(entry) != LEDGER_ENTRY_FIELDS
        ):
            raise ValueError("portfolio_credit_ledger_inconsistent")
        try:
            credit_document = entry["credit"]
            if (
                type(credit_document) is not dict
                or set(credit_document) != CREDIT_FIELDS
            ):
                raise ValueError("portfolio_credit_ledger_inconsistent")
            application = PortfolioCreditApplication(
                application_id=entry["application_id"],
                credit_id=entry["credit_id"],
                object_name=entry["object_name"],
                destination_kind=PortfolioCreditDestinationKind(
                    entry["destination_kind"]
                ),
                applied_duration=_duration(entry["applied_duration_us"]),
                applied_at=_timestamp(entry["applied_at"]),
            )
            evidence_ids = credit_document["evidence_ids"]
            if not isinstance(evidence_ids, list):
                raise ValueError("portfolio_credit_ledger_inconsistent")
            credit = PortfolioCredit(
                credit_id=credit_id,
                execution_id=credit_document["execution_id"],
                evidence_ids=tuple(evidence_ids),
                usable_integration_duration=_duration(
                    credit_document["usable_integration_duration_us"]
                ),
                credited_at=_timestamp(credit_document["credited_at"]),
            )
        except (KeyError, OverflowError, TypeError, ValueError) as exc:
            if str(exc) == "portfolio_credit_ledger_inconsistent":
                raise
            raise ValueError("portfolio_credit_ledger_inconsistent") from exc
        if (
            application.credit_id != credit_id
            or application.applied_duration
            != credit.usable_integration_duration
            or application.application_id in application_ids
        ):
            raise ValueError("portfolio_credit_ledger_inconsistent")
        if application.destination_kind is PortfolioCreditDestinationKind.PROJECT:
            projects = profile.get("projects", {})
            if (
                type(projects) is not dict
                or application.object_name not in projects
            ):
                raise ValueError("portfolio_credit_ledger_inconsistent")
        application_ids.add(application.application_id)
        applications[credit_id] = application
        credits[credit_id] = credit
    return applications, credits


def _validate_project_capacity(
    application: PortfolioCreditApplication,
    credit: PortfolioCredit,
    projects: dict[str, dict],
) -> None:
    if application.destination_kind is not PortfolioCreditDestinationKind.PROJECT:
        return
    project = projects.get(application.object_name)
    if project is None:
        return
    if type(project) is not dict:
        raise TypeError("project_record_must_be_dict")
    if "target_hours" not in project:
        return
    current_hours = project.get("hours", 0.0)
    target_hours = project["target_hours"]
    if (
        isinstance(current_hours, bool)
        or not isinstance(current_hours, (int, float))
        or not math.isfinite(current_hours)
        or current_hours < 0
    ):
        raise ValueError("project_hours_invalid")
    if (
        isinstance(target_hours, bool)
        or not isinstance(target_hours, (int, float))
        or not math.isfinite(target_hours)
        or target_hours < 0
    ):
        raise ValueError("project_target_hours_invalid")
    added_hours = credit.usable_integration_duration.total_seconds() / 3600
    if current_hours + added_hours > target_hours:
        raise ValueError("project_capacity_exceeded")


class DurablePortfolioCreditApplicationService:
    def __init__(
        self,
        *,
        load_profile: Callable[[], Mapping],
        save_profile: Callable[[dict], object],
        execution_loader: Callable[[str], Execution | None],
        evidence_loader: Callable[[str], OutcomeEvidence | None],
    ) -> None:
        self.load_profile = load_profile
        self.save_profile = save_profile
        self.execution_loader = execution_loader
        self.evidence_loader = evidence_loader

    def apply(
        self,
        application: PortfolioCreditApplication,
        credit: PortfolioCredit,
    ) -> PortfolioCreditApplicationResult:
        if type(application) is not PortfolioCreditApplication:
            raise TypeError("application_must_be_portfolio_credit_application")
        if type(credit) is not PortfolioCredit:
            raise TypeError("credit_must_be_portfolio_credit")
        if application.credit_id != credit.credit_id:
            raise ValueError("credit_id_mismatch")
        if application.applied_duration != credit.usable_integration_duration:
            raise ValueError("applied_duration_mismatch")

        persisted_profile = self.load_profile()
        if not isinstance(persisted_profile, Mapping):
            raise TypeError("profile_must_be_mapping")
        profile = deepcopy(dict(persisted_profile))
        applications, credits = _load_ledger(profile)
        prior_credit = credits.get(credit.credit_id)
        if prior_credit is not None:
            if prior_credit != credit:
                raise ValueError("portfolio_credit_ledger_inconsistent")
            return apply_portfolio_credit(
                application,
                credit,
                profile.get("projects", {}),
                applications,
            )

        execution = self.execution_loader(credit.execution_id)
        if execution is None:
            raise ValueError("execution_not_found")
        evidence_records = tuple(
            self.evidence_loader(evidence_id) for evidence_id in credit.evidence_ids
        )
        if any(record is None for record in evidence_records):
            raise ValueError("evidence_not_found")
        validate_portfolio_credit(credit, execution, evidence_records)

        projects = profile.get("projects")
        if type(projects) is not dict:
            raise TypeError("projects_must_be_dict")
        _validate_project_capacity(application, credit, projects)
        result = apply_portfolio_credit(
            application,
            credit,
            projects,
            applications,
        )
        credits[credit.credit_id] = credit
        profile[LEDGER_FIELD] = {
            recorded_credit_id: _ledger_entry(
                recorded_application,
                credits[recorded_credit_id],
            )
            for recorded_credit_id, recorded_application in applications.items()
        }
        self.save_profile(profile)
        if result.outcome is not PortfolioCreditApplicationOutcome.APPLIED:
            raise ValueError("portfolio_credit_ledger_inconsistent")
        return result
