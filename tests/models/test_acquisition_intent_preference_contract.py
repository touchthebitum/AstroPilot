from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.acquisition_intent_preference import (
    ACQUISITION_INTENT_PREFERENCE_REASON_CODES,
    LUNAR_CONTAMINATION_EQUIVALENT,
    LUNAR_CONTAMINATION_INCOMPARABLE,
    LOWER_LUNAR_CONTAMINATION,
    AcquisitionIntentPreference,
    AcquisitionIntentPreferenceStatus,
)


def _preference(**overrides) -> AcquisitionIntentPreference:
    values = {
        "left_acquisition_intent_id": "left-intent",
        "right_acquisition_intent_id": "right-intent",
        "status": AcquisitionIntentPreferenceStatus.LEFT_PREFERRED,
        "reason_codes": (LOWER_LUNAR_CONTAMINATION,),
    }
    values.update(overrides)
    return AcquisitionIntentPreference(**values)


def test_result_contract_is_exact_immutable_and_preserves_ids():
    preference = _preference(
        left_acquisition_intent_id=" left-intent ",
        right_acquisition_intent_id=" right-intent ",
    )

    assert tuple(field.name for field in fields(preference)) == (
        "left_acquisition_intent_id",
        "right_acquisition_intent_id",
        "status",
        "reason_codes",
    )
    assert preference.left_acquisition_intent_id == " left-intent "
    assert preference.right_acquisition_intent_id == " right-intent "
    with pytest.raises((FrozenInstanceError, AttributeError)):
        preference.status = AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED


def test_status_and_reason_code_contracts_are_exact():
    assert tuple(AcquisitionIntentPreferenceStatus) == (
        AcquisitionIntentPreferenceStatus.LEFT_PREFERRED,
        AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED,
        AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE,
    )
    assert ACQUISITION_INTENT_PREFERENCE_REASON_CODES == (
        LOWER_LUNAR_CONTAMINATION,
        LUNAR_CONTAMINATION_EQUIVALENT,
        LUNAR_CONTAMINATION_INCOMPARABLE,
    )


@pytest.mark.parametrize(
    "field_name",
    ["left_acquisition_intent_id", "right_acquisition_intent_id"],
)
@pytest.mark.parametrize("value", [None, 42, "", "   "])
def test_rejects_invalid_intent_ids(field_name, value):
    with pytest.raises((TypeError, ValueError), match=field_name):
        _preference(**{field_name: value})


@pytest.mark.parametrize("status", [None, "left_preferred", 1])
def test_rejects_invalid_status(status):
    with pytest.raises(TypeError, match="status"):
        _preference(status=status)


@pytest.mark.parametrize(
    "reason_codes",
    [
        None,
        [LOWER_LUNAR_CONTAMINATION],
        (1,),
        (),
        (LOWER_LUNAR_CONTAMINATION, LOWER_LUNAR_CONTAMINATION),
        ("OTHER_REASON",),
    ],
)
def test_rejects_invalid_reason_codes(reason_codes):
    with pytest.raises((TypeError, ValueError), match="reason"):
        _preference(reason_codes=reason_codes)


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (
            AcquisitionIntentPreferenceStatus.LEFT_PREFERRED,
            LUNAR_CONTAMINATION_EQUIVALENT,
        ),
        (
            AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED,
            LUNAR_CONTAMINATION_INCOMPARABLE,
        ),
        (
            AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE,
            LOWER_LUNAR_CONTAMINATION,
        ),
    ],
)
def test_rejects_reason_codes_inconsistent_with_status(status, reason_code):
    with pytest.raises(ValueError, match="inconsistent"):
        _preference(status=status, reason_codes=(reason_code,))
