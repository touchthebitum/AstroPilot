"""Immutable record of a PortfolioCredit application attempt that took effect."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class PortfolioCreditDestinationKind(str, Enum):
    PROJECT = "project"
    TARGET = "target"


class PortfolioCreditApplicationOutcome(str, Enum):
    APPLIED = "applied"
    ALREADY_APPLIED = "already_applied"


@dataclass(frozen=True, slots=True)
class PortfolioCreditApplication:
    """Traceable application using the existing object-name destination identity."""

    application_id: str
    credit_id: str
    object_name: str
    destination_kind: PortfolioCreditDestinationKind
    applied_duration: timedelta
    applied_at: datetime

    def __post_init__(self) -> None:
        for name in ("application_id", "credit_id", "object_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not isinstance(self.destination_kind, PortfolioCreditDestinationKind):
            raise TypeError("Expected PortfolioCreditDestinationKind")
        if not isinstance(self.applied_duration, timedelta):
            raise TypeError("applied_duration_must_be_timedelta")
        if self.applied_duration < timedelta(0):
            raise ValueError("applied_duration_must_be_non_negative")
        if not isinstance(self.applied_at, datetime):
            raise TypeError("applied_at_must_be_datetime")
        if self.applied_at.tzinfo is None or self.applied_at.utcoffset() is None:
            raise ValueError("applied_at_timezone_required")


@dataclass(frozen=True, slots=True)
class PortfolioCreditApplicationResult:
    """Distinguishes a new application from a canonical prior application."""

    application: PortfolioCreditApplication
    outcome: PortfolioCreditApplicationOutcome

    def __post_init__(self) -> None:
        if type(self.application) is not PortfolioCreditApplication:
            raise TypeError("application_must_be_portfolio_credit_application")
        if not isinstance(self.outcome, PortfolioCreditApplicationOutcome):
            raise TypeError("Expected PortfolioCreditApplicationOutcome")
