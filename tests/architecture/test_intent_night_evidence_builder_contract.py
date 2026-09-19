from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from decision.models.context.site_context import SiteContext
from decision.models.imaging_field_geometry import (
    ImagingFieldGeometryDefinition,
)
from decision.models.lunar_geometry import LunarGeometry
from decision.services.imaging_field_geometry_resolver import (
    ImagingFieldGeometryResolver,
)
from decision.services.intent_night_evidence_builder import (
    IntentNightEvidenceBuildError,
    IntentNightEvidenceBuilder,
)
from decision.services.lunar_geometry_service import LunarGeometryService


FIELD = ImagingFieldGeometryDefinition(
    imaging_field_id="sh2-129_ou4",
    reference_ra_deg=317.95,
    reference_dec_deg=59.97,
)
SITE = SiteContext(
    name="Buttes",
    latitude=46.7508,
    longitude=6.5495,
    elevation=770.0,
    bortle=4,
)


class StubLunarGeometryService:
    def __init__(self, result: LunarGeometry) -> None:
        self.result = result
        self.calls = []

    def calculate(self, **kwargs) -> LunarGeometry:
        self.calls.append(kwargs)
        return self.result


class FailingLunarGeometryService:
    def calculate(self, **kwargs) -> LunarGeometry:
        raise RuntimeError("ephemeris unavailable")


def _builder(lunar_geometry_service):
    return IntentNightEvidenceBuilder(
        geometry_resolver=ImagingFieldGeometryResolver([FIELD]),
        lunar_geometry_service=lunar_geometry_service,
    )


def test_builder_derives_duration_midpoint_and_exact_lunar_values_once():
    lunar_result = LunarGeometry(0.61, 24.5, 73.25)
    lunar_service = StubLunarGeometryService(lunar_result)
    builder = _builder(lunar_service)
    start = datetime(
        2024,
        10,
        15,
        20,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )
    end = datetime(
        2024,
        10,
        16,
        1,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )

    evidence = builder.build(
        imaging_field_id="sh2-129_ou4",
        actionable_window_start=start,
        actionable_window_end=end,
        site=SITE,
    )

    expected_midpoint = datetime(
        2024,
        10,
        15,
        20,
        30,
        tzinfo=timezone.utc,
    )
    assert evidence.actionable_window_start is start
    assert evidence.actionable_window_end is end
    assert evidence.actionable_duration_hours == 5.0
    assert evidence.reference_time == expected_midpoint
    assert evidence.moon_illumination == lunar_result.moon_illumination
    assert evidence.moon_altitude_deg == lunar_result.moon_altitude_deg
    assert evidence.moon_separation_deg == lunar_result.moon_separation_deg
    assert len(lunar_service.calls) == 1
    assert lunar_service.calls[0] == {
        "reference_time": expected_midpoint,
        "site": SITE,
        "field_geometry": FIELD,
    }


def test_builder_uses_utc_elapsed_time_across_offset_change():
    lunar_service = StubLunarGeometryService(LunarGeometry(0.5, 0.0, 90.0))
    builder = _builder(lunar_service)
    zurich = ZoneInfo("Europe/Zurich")
    start = datetime(2024, 10, 27, 1, 30, tzinfo=zurich)
    end = datetime(2024, 10, 27, 3, 30, tzinfo=zurich)

    evidence = builder.build(
        imaging_field_id="sh2-129_ou4",
        actionable_window_start=start,
        actionable_window_end=end,
        site=SITE,
    )

    assert evidence.actionable_duration_hours == 3.0
    assert evidence.reference_time == datetime(
        2024,
        10,
        27,
        1,
        0,
        tzinfo=timezone.utc,
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2024, 1, 1), datetime(2024, 1, 2, tzinfo=timezone.utc)),
        (datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2)),
        (
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
    ],
)
def test_builder_fails_closed_for_invalid_windows(start, end):
    with pytest.raises(IntentNightEvidenceBuildError):
        _builder(StubLunarGeometryService(LunarGeometry(0.5, 0.0, 90.0))).build(
            imaging_field_id="sh2-129_ou4",
            actionable_window_start=start,
            actionable_window_end=end,
            site=SITE,
        )


def test_builder_fails_closed_for_unknown_geometry_without_lunar_call():
    lunar_service = StubLunarGeometryService(LunarGeometry(0.5, 0.0, 90.0))

    with pytest.raises(IntentNightEvidenceBuildError, match="resolve"):
        _builder(lunar_service).build(
            imaging_field_id="unknown",
            actionable_window_start=datetime(
                2024, 1, 1, tzinfo=timezone.utc
            ),
            actionable_window_end=datetime(
                2024, 1, 1, 1, tzinfo=timezone.utc
            ),
            site=SITE,
        )

    assert lunar_service.calls == []


@pytest.mark.parametrize("invalid_site", [object(), replace(SITE, latitude=91.0)])
def test_builder_fails_closed_for_invalid_site(invalid_site):
    with pytest.raises(IntentNightEvidenceBuildError, match="site|lunar"):
        _builder(LunarGeometryService()).build(
            imaging_field_id="sh2-129_ou4",
            actionable_window_start=datetime(
                2024, 1, 1, tzinfo=timezone.utc
            ),
            actionable_window_end=datetime(
                2024, 1, 1, 1, tzinfo=timezone.utc
            ),
            site=invalid_site,
        )


def test_builder_propagates_lunar_failure_as_dedicated_error_not_none():
    with pytest.raises(
        IntentNightEvidenceBuildError,
        match="calculate lunar geometry",
    ) as caught:
        _builder(FailingLunarGeometryService()).build(
            imaging_field_id="sh2-129_ou4",
            actionable_window_start=datetime(
                2024, 1, 1, tzinfo=timezone.utc
            ),
            actionable_window_end=datetime(
                2024, 1, 1, 1, tzinfo=timezone.utc
            ),
            site=SITE,
        )

    assert isinstance(caught.value.__cause__, RuntimeError)


def test_builder_source_has_no_legacy_scoring_or_preference_dependencies():
    source = Path(
        "decision/services/intent_night_evidence_builder.py"
    ).read_text(encoding="utf-8")

    for forbidden_dependency in (
        "CATALOG",
        "SkyEngine",
        "moon_penalty",
        "filter_selection",
        "target_semantics",
        "AcquisitionIntentPreference",
        "AcquisitionIntentEligibility",
        "ranking",
        "score",
    ):
        assert forbidden_dependency not in source
