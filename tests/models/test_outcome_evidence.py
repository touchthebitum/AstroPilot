from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)


OBSERVED_AT = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
KINDS = (
    (FieldOutcomeEvidence, OutcomeEvidenceCategory.FIELD),
    (TechnicalOutcomeEvidence, OutcomeEvidenceCategory.TECHNICAL),
    (AcquisitionOutcomeEvidence, OutcomeEvidenceCategory.ACQUISITION),
    (ImageOutcomeEvidence, OutcomeEvidenceCategory.IMAGE),
)
PROVENANCE = {"evidence_id", "execution_id", "category", "observed_at", "source"}
DURATIONS = ("actual_capture_duration", "usable_integration_duration")


def provenance(category):
    return {
        "evidence_id": "evidence-1",
        "execution_id": "execution-1",
        "category": category,
        "observed_at": OBSERVED_AT,
        "source": OutcomeEvidenceSource.USER,
    }


@pytest.mark.parametrize("kind,category", KINDS)
def test_valid_category_specific_evidence(kind, category):
    record = kind(**provenance(category))
    assert isinstance(record, OutcomeEvidence)
    assert record.evidence_id == "evidence-1"
    assert record.execution_id == "execution-1"
    assert record.category is category
    assert record.observed_at is OBSERVED_AT
    assert record.source is OutcomeEvidenceSource.USER


def test_explicit_category_and_minimal_source_contract():
    assert {member.name for member in OutcomeEvidenceCategory} == {
        "FIELD", "TECHNICAL", "ACQUISITION", "IMAGE"
    }
    assert {member.name for member in OutcomeEvidenceSource} == {"USER"}


@pytest.mark.parametrize("name", ["evidence_id", "execution_id"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 1, True, [], {}])
def test_invalid_identifiers_rejected(name, value):
    values = provenance(OutcomeEvidenceCategory.FIELD)
    values[name] = value
    with pytest.raises((TypeError, ValueError)):
        FieldOutcomeEvidence(**values)


class NoOffsetTimezone(tzinfo):
    def utcoffset(self, dt):
        return None


@pytest.mark.parametrize("value", [
    datetime(2026, 9, 10),
    datetime(2026, 9, 10, tzinfo=NoOffsetTimezone()),
    "2026-09-10T22:00:00+00:00", None, 0,
])
def test_invalid_or_naive_observed_at_rejected(value):
    values = provenance(OutcomeEvidenceCategory.FIELD)
    values["observed_at"] = value
    with pytest.raises((TypeError, ValueError)):
        FieldOutcomeEvidence(**values)


def test_aware_non_utc_timestamp_preserved():
    values = provenance(OutcomeEvidenceCategory.FIELD)
    values["observed_at"] = OBSERVED_AT.astimezone(timezone(timedelta(hours=2)))
    assert FieldOutcomeEvidence(**values).observed_at is values["observed_at"]


@pytest.mark.parametrize("kind,category", KINDS)
@pytest.mark.parametrize("name", sorted(PROVENANCE))
def test_provenance_required_without_hidden_defaults(kind, category, name):
    values = provenance(category)
    del values[name]
    with pytest.raises(TypeError):
        kind(**values)


@pytest.mark.parametrize("kind,category", KINDS)
def test_all_fields_immutable(kind, category):
    record = kind(**provenance(category))
    for field in fields(record):
        with pytest.raises(FrozenInstanceError):
            setattr(record, field.name, getattr(record, field.name))
        with pytest.raises(FrozenInstanceError):
            delattr(record, field.name)
    with pytest.raises((AttributeError, TypeError)):
        record.payload = {}


@pytest.mark.parametrize("kind,category", KINDS)
def test_category_mismatch_and_untyped_category_rejected(kind, category):
    for invalid in [member for member in OutcomeEvidenceCategory if member is not category] + [
        category.value, None, "unsupported", {}
    ]:
        values = provenance(invalid)
        with pytest.raises((TypeError, ValueError)):
            kind(**values)


@pytest.mark.parametrize("kind,category", KINDS)
@pytest.mark.parametrize("source", ["user", "system", "import", None, 1, {}])
def test_unverified_or_untyped_source_rejected(kind, category, source):
    values = provenance(category)
    values["source"] = source
    with pytest.raises((TypeError, ValueError)):
        kind(**values)


@pytest.mark.parametrize("kind,category", KINDS)
def test_no_generic_payload_verdict_credit_or_learning_contract(kind, category):
    expected = PROVENANCE | (set(DURATIONS) if kind is AcquisitionOutcomeEvidence else set())
    assert {field.name for field in fields(kind)} == expected
    for unsupported in (
        "payload", "metadata", "success", "failure", "verdict", "assessment",
        "score", "confidence", "recommendation", "portfolio_credit", "learning",
        "project_progress", "execution",
    ):
        with pytest.raises(TypeError):
            kind(**provenance(category), **{unsupported: {}})


def test_generic_and_unsupported_evidence_types_rejected():
    with pytest.raises(TypeError):
        OutcomeEvidence(**provenance(OutcomeEvidenceCategory.FIELD))

    class UnsupportedFieldEvidence(FieldOutcomeEvidence):
        pass

    with pytest.raises(TypeError):
        UnsupportedFieldEvidence(**provenance(OutcomeEvidenceCategory.FIELD))


def test_acquisition_durations_are_distinct_explicit_facts():
    record = AcquisitionOutcomeEvidence(
        **provenance(OutcomeEvidenceCategory.ACQUISITION),
        actual_capture_duration=timedelta(minutes=50),
        usable_integration_duration=timedelta(minutes=30),
    )
    assert record.actual_capture_duration == timedelta(minutes=50)
    assert record.usable_integration_duration == timedelta(minutes=30)


@pytest.mark.parametrize("name", DURATIONS)
@pytest.mark.parametrize("duration", [timedelta(0), timedelta(minutes=30)])
def test_one_duration_never_supplies_the_other(name, duration):
    record = AcquisitionOutcomeEvidence(
        **provenance(OutcomeEvidenceCategory.ACQUISITION), **{name: duration}
    )
    assert getattr(record, name) == duration
    other = next(field for field in DURATIONS if field != name)
    assert getattr(record, other) is None


@pytest.mark.parametrize("name", DURATIONS)
@pytest.mark.parametrize("value", [timedelta(microseconds=-1), -1, 0, True, "30", {}, float("nan")])
def test_negative_or_untyped_acquisition_durations_rejected(name, value):
    with pytest.raises((TypeError, ValueError)):
        AcquisitionOutcomeEvidence(
            **provenance(OutcomeEvidenceCategory.ACQUISITION), **{name: value}
        )


@pytest.mark.parametrize("status", list(ExecutionStatus))
def test_evidence_does_not_mutate_or_confirm_execution_or_infer_duration(status):
    start = end = duration = None
    if status is ExecutionStatus.IN_PROGRESS:
        start = OBSERVED_AT
    elif status in (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED):
        start = OBSERVED_AT - timedelta(hours=1)
        end = OBSERVED_AT
        duration = timedelta(hours=1)
    execution = Execution("execution-1", "mission-1", status, start, end, duration)
    before = asdict(execution)
    records: tuple[OutcomeEvidence, ...] = ()
    assert records == ()
    assert asdict(execution) == before
    for kind, category in KINDS:
        record = kind(**provenance(category))
        assert record.execution_id == execution.execution_id
        assert asdict(execution) == before
        assert execution.status is status
        if isinstance(record, AcquisitionOutcomeEvidence):
            assert record.actual_capture_duration is None
            assert record.usable_integration_duration is None
    assert records == ()
    assert ExecutionStatus.UNCONFIRMED is not ExecutionStatus.COMPLETED
