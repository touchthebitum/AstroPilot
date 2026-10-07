from dataclasses import replace
from types import SimpleNamespace

import pytest

from decision.quality.astro_quality_context import AstroQualityContext
from decision.quality.astro_quality_engine import AstroQualityEngine
from decision.quality.astro_quality_result import AstroQualityResult
from decision.acceptance_lineage_persistence import _encode, _decode

FULL = AstroQualityContext(75, 0, 0, 1.2, 9, 100)
FIELDS = (
    ("target_altitude_deg", 0, "altitude"),
    ("cloud_cover_percent", 100, "clouds"),
    ("moon_penalty", 1, "moon"),
    ("seeing_arcsec", 5, "seeing"),
    ("image_quality_score", 0, "setup"),
    ("dew_score", 20, "dew"),
)


@pytest.mark.parametrize("field,adverse,name", FIELDS)
@pytest.mark.parametrize("adverse_value", [True, False])
def test_removal_never_promotes_a_decision_score(field, adverse, name, adverse_value):
    context = replace(FULL, **{field: adverse}) if adverse_value else FULL
    known = AstroQualityEngine.evaluate(context)
    unknown = AstroQualityEngine.evaluate(replace(context, **{field: None}))
    assert known.decision_eligible
    assert known.decision_score == known.score
    assert unknown.decision_score is None
    assert not unknown.decision_eligible
    assert unknown.status == "insufficient_evidence"
    assert unknown.missing_metrics == (name,)
    assert unknown.completeness == round(1 - AstroQualityEngine.WEIGHTS[name], 2)
    assert unknown.confidence == unknown.completeness


@pytest.mark.parametrize("field,adverse,name", FIELDS)
@pytest.mark.parametrize("invalid", [float('nan'), float('inf'), 'unknown', True])
def test_invalid_metric_is_unknown(field, adverse, name, invalid):
    result = AstroQualityEngine.evaluate(replace(FULL, **{field: invalid}))
    assert name in result.missing_metrics
    assert result.decision_score is None


def test_renormalized_diagnostic_is_explicitly_non_comparable():
    adverse = AstroQualityEngine.evaluate(replace(FULL, dew_score=20))
    partial = AstroQualityEngine.evaluate(replace(FULL, dew_score=None))
    assert partial.score > adverse.score
    assert partial.decision_score is None


def test_empty_helper_context_is_not_favorable():
    result = AstroQualityEngine.evaluate(SimpleNamespace())
    assert result.completeness == 0
    assert len(result.missing_metrics) == 6
    assert result.decision_score is None
    assert result.limiting_factor is None


def test_legacy_read_preserves_score_without_claiming_eligibility():
    document = _encode(AstroQualityResult(91, 1))
    document['fields'] = {key: value for key, value in document['fields'].items()
                          if key in {'score', 'confidence', 'metrics', 'limiting_factor'}}
    restored = _decode(document)
    assert restored.score == 91
    assert restored.confidence == 1
    assert not restored.decision_eligible
    assert restored.decision_score is None


def test_full_and_partial_roundtrip_preserves_contract():
    for context in (FULL, replace(FULL, seeing_arcsec=None)):
        result = AstroQualityEngine.evaluate(context)
        assert _decode(_encode(result)) == result


def test_image_setup_unknown_inputs_cannot_be_counted_as_full_evidence():
    from decision.engines.image_quality_engine import ImageQualityEngine
    complete = dict(object_name='M31', object_type='galaxy', object_size_arcmin=100,
                    seeing=2, sampling=1)
    assert ImageQualityEngine.evaluate(complete).confidence == 1
    for field in ('seeing', 'sampling', 'object_size_arcmin'):
        result = ImageQualityEngine.evaluate({**complete, field: None})
        assert result.confidence == 0


def test_candidate_model_does_not_transport_aqi_as_a_ranking_score():
    from dataclasses import fields
    from decision.models.candidate import Candidate
    assert 'astro_quality' not in {field.name for field in fields(Candidate)}
    # Candidate astro_score is the rule-based astronomy score, not the post-selection AQI.
