"""Atomic, idempotent application of validated credit to existing project state.

The caller owns persistence for both dictionaries. Target-only applications are
recorded without creating a project because no mutable target portfolio store exists.
"""

import math

from decision.models.portfolio_credit import PortfolioCredit
from decision.models.portfolio_credit_application import (
    PortfolioCreditApplication,
    PortfolioCreditApplicationOutcome,
    PortfolioCreditApplicationResult,
    PortfolioCreditDestinationKind,
)


def apply_portfolio_credit(
    application: PortfolioCreditApplication,
    credit: PortfolioCredit,
    projects: dict[str, dict],
    applications_by_credit_id: dict[str, PortfolioCreditApplication],
) -> PortfolioCreditApplicationResult:
    """Apply credit once, mutating only project hours and the application registry."""

    if type(application) is not PortfolioCreditApplication:
        raise TypeError("application_must_be_portfolio_credit_application")
    if type(credit) is not PortfolioCredit:
        raise TypeError("credit_must_be_portfolio_credit")
    if type(projects) is not dict:
        raise TypeError("projects_must_be_dict")
    if type(applications_by_credit_id) is not dict:
        raise TypeError("applications_by_credit_id_must_be_dict")
    if application.credit_id != credit.credit_id:
        raise ValueError("credit_id_mismatch")
    if application.applied_duration != credit.usable_integration_duration:
        raise ValueError("applied_duration_mismatch")

    for recorded_credit_id, recorded_application in applications_by_credit_id.items():
        if (
            not isinstance(recorded_credit_id, str)
            or type(recorded_application) is not PortfolioCreditApplication
            or recorded_application.credit_id != recorded_credit_id
        ):
            raise ValueError("application_state_inconsistent")

    prior_application = applications_by_credit_id.get(credit.credit_id)
    if prior_application is not None:
        if prior_application.applied_duration != credit.usable_integration_duration:
            raise ValueError("application_state_inconsistent")
        return PortfolioCreditApplicationResult(
            application=prior_application,
            outcome=PortfolioCreditApplicationOutcome.ALREADY_APPLIED,
        )

    project_record = None
    prior_hours = None
    hours_was_present = False
    updated_hours = None
    if application.destination_kind is PortfolioCreditDestinationKind.PROJECT:
        project_record = projects.get(application.object_name)
        if project_record is None:
            raise ValueError("project_destination_unresolved")
        if type(project_record) is not dict:
            raise TypeError("project_record_must_be_dict")
        hours_was_present = "hours" in project_record
        prior_hours = project_record.get("hours", 0.0)
        if (
            isinstance(prior_hours, bool)
            or not isinstance(prior_hours, (int, float))
            or not math.isfinite(prior_hours)
            or prior_hours < 0
        ):
            raise ValueError("project_hours_invalid")
        added_hours = credit.usable_integration_duration.total_seconds() / 3600
        updated_hours = prior_hours + added_hours

    try:
        applications_by_credit_id[credit.credit_id] = application
        if project_record is not None:
            project_record["hours"] = updated_hours
    except Exception:
        applications_by_credit_id.pop(credit.credit_id, None)
        if project_record is not None:
            if hours_was_present:
                project_record["hours"] = prior_hours
            else:
                project_record.pop("hours", None)
        raise

    return PortfolioCreditApplicationResult(
        application=application,
        outcome=PortfolioCreditApplicationOutcome.APPLIED,
    )
