from types import SimpleNamespace

from astro_score import build_decision_engine
from decision.rules.image_quality_rule import ImageQualityRule
from decision.rules.resolution_rule import ResolutionRule
from decision.rules.sampling_rule import SamplingRule


TECHNICAL_RULE_TYPES = (SamplingRule, ResolutionRule, ImageQualityRule)


def test_production_engine_uses_only_independent_technical_rules():
    engine = build_decision_engine()
    technical_rule_types = {
        type(rule)
        for rule in engine.rules
        if isinstance(rule, TECHNICAL_RULE_TYPES)
    }

    assert technical_rule_types == {SamplingRule, ResolutionRule}


def test_production_engine_emits_no_derived_image_quality_contribution(
    monkeypatch,
    frozen_equipment,
):
    engine = build_decision_engine()
    context = SimpleNamespace(
        equipment=frozen_equipment,
        sky=SimpleNamespace(
            target=SimpleNamespace(
                name="M31",
                object_type="galaxy",
                angular_size_arcmin=190.0,
            ),
        ),
        weather=SimpleNamespace(seeing_arcsec=3.2),
    )

    for rule in engine.rules:
        if not isinstance(rule, TECHNICAL_RULE_TYPES):
            monkeypatch.setattr(rule, "evaluate", lambda context, profile: None)

    contributions, _ = engine.evaluate(context, profile={})

    assert {contribution.rule for contribution in contributions} == {
        "Sampling",
        "Resolution",
    }
