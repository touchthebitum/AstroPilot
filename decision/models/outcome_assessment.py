"""Immutable assessment of explicitly supplied outcome evidence."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OutcomeAssessmentStatus(str, Enum):
    """Describes evidence sufficiency, never overall session quality."""

    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _validate_identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}_required")


def _validate_evidence_ids(evidence_ids: object, *, allow_empty: bool) -> None:
    if not isinstance(evidence_ids, tuple):
        raise TypeError("evidence_ids_must_be_tuple")
    if not allow_empty and not evidence_ids:
        raise ValueError("evidence_required")
    for evidence_id in evidence_ids:
        _validate_identifier("evidence_id", evidence_id)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("duplicate_evidence_id")


@dataclass(frozen=True, slots=True)
class OutcomeFinding:
    """A stable finding basis traced to the evidence that supports it."""

    finding_id: str
    basis: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_identifier("finding_id", self.finding_id)
        _validate_identifier("finding_basis", self.basis)
        _validate_evidence_ids(self.evidence_ids, allow_empty=False)


@dataclass(frozen=True, slots=True)
class OutcomeAssessment:
    """Explicit findings and evidence-sufficiency status for one execution."""

    assessment_id: str
    execution_id: str
    evidence_ids: tuple[str, ...]
    assessed_at: datetime
    status: OutcomeAssessmentStatus
    findings: tuple[OutcomeFinding, ...]

    def __post_init__(self) -> None:
        _validate_identifier("assessment_id", self.assessment_id)
        _validate_identifier("execution_id", self.execution_id)
        _validate_evidence_ids(self.evidence_ids, allow_empty=False)
        if not isinstance(self.assessed_at, datetime):
            raise TypeError("assessed_at_must_be_datetime")
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at_timezone_required")
        if not isinstance(self.status, OutcomeAssessmentStatus):
            raise TypeError("Expected OutcomeAssessmentStatus")
        if not isinstance(self.findings, tuple):
            raise TypeError("findings_must_be_tuple")
        if not all(type(finding) is OutcomeFinding for finding in self.findings):
            raise TypeError("findings_must_contain_outcome_findings")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("duplicate_finding_id")
        assessment_evidence_ids = set(self.evidence_ids)
        for finding in self.findings:
            if not set(finding.evidence_ids).issubset(assessment_evidence_ids):
                raise ValueError("finding_evidence_not_in_assessment")
