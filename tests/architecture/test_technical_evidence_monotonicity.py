"""Evidence deletion through real models, rules, weighted engine and candidates."""
from types import SimpleNamespace as NS

import pytest

from decision.decision_engine import DecisionEngine
from decision.engines.image_quality_engine import ImageQualityEngine
from decision.models.sampling_model import SamplingModel
from decision.models.resolution_model import ResolutionModel
from decision.rules.seeing_rule import SeeingRule
from decision.rules.sampling_rule import SamplingRule
from decision.rules.resolution_rule import ResolutionRule


def context(seeing, size, sampling=1):
    # Real SetupCalculator, with a focal length chosen for this pixel scale.
    return NS(weather=NS(seeing_arcsec=seeing),
        sky=NS(target=NS(name="M31", object_type="galaxy", angular_size_arcmin=size)),
        equipment=NS(setup=NS(camera=NS(pixel_size_um=sampling, sensor_width_px=1000,
            sensor_height_px=1000), optics=NS(focal_length_mm=206.265,
            focal_ratio=4, aperture_mm=50))))


@pytest.mark.parametrize("seeing", [0.2, 0.7, 1.2, 1.7, 2.5, 3.5, 10])
@pytest.mark.parametrize("size", [0.1, 1, 3, 6, 15, 90, 190])
@pytest.mark.parametrize("removed", ["seeing", "size"])
@pytest.mark.parametrize("weight", [0, 0.25, 1, 3])
def test_rule_total_and_real_candidate_never_improve(seeing, size, removed, weight):
    import astro_score
    engine = DecisionEngine()
    for rule in (SeeingRule(), SamplingRule(), ResolutionRule()):
        engine.add_rule(rule)
    profile = {"decision_weights": {"seeing": weight, "sampling": weight, "resolution": weight},
        "preferences": {"bortle": 4}, "projects": {"M31": {
            "hours": 9, "target_hours": 10, "importance": 5}},
        "active_equipment": "samyang_183", "available_equipment": ["samyang_183"]}
    known = context(seeing, size)
    missing = context(None if removed == "seeing" else seeing, None if removed == "size" else size)
    before = engine.evaluate(known, profile)[1]
    contributions, after = engine.evaluate(missing, profile)
    assert after <= before
    assert any(c.evidence_status == "unknown" for c in contributions)
    candidates = [astro_score.recommend_project_for_night([
        {"name": "M31", "catalog_key": "M31", "global_score": 80 + score}],
        available_hours=2, profile=profile)[0] for score in (before, after)]
    assert candidates[1].global_score <= candidates[0].global_score
    assert candidates[1].decision_score <= candidates[0].decision_score
    assert candidates[1].final_score <= candidates[0].final_score


@pytest.mark.parametrize("seeing", [0.2, 0.7, 1.5, 2.5, 4])
@pytest.mark.parametrize("size", [0.1, 1, 5, 15, 90, 190])
@pytest.mark.parametrize("removed", ["seeing", "sampling", "object_size_arcmin"])
def test_dictionary_service_and_helpers_never_improve(seeing, size, removed):
    data = {"object_name": "M31", "object_type": "galaxy", "seeing": seeing,
        "sampling": 1, "object_size_arcmin": size}
    known = ImageQualityEngine.evaluate(data)
    data[removed] = None
    unknown = ImageQualityEngine.evaluate(data)
    assert unknown.score <= known.score
    assert unknown.metrics["evidence_status"] == "unknown"
    assert unknown.confidence == 0


def test_known_neutral_favorable_and_adverse_remain_distinct():
    rule = SeeingRule()
    assert [(rule.evaluate(context(s, 1), {}).score,
        rule.evaluate(context(s, 1), {}).evidence_status) for s in (None, 2.5, 1.2, 4)] == [
            (-10, "unknown"), (0, "known"), (15, "known"), (-10, "known")]


def test_missing_sampling_rule_branch_and_helper_bounds(monkeypatch):
    from decision.calculators.setup_calculator import SetupCalculator
    monkeypatch.setattr(SetupCalculator, "compute", lambda setup: NS(sampling_arcsec_per_pixel=None))
    unknown = SamplingRule().evaluate(context(1.5, 190), {})
    assert unknown.score == -6 and unknown.evidence_status == "unknown"
    for size in (1, 190, None):
        assert SamplingModel.evaluate("M31", "galaxy", size, None, 1).score == -6
    assert ResolutionModel.evaluate("galaxy", None, 1).score == -10


@pytest.mark.parametrize("weight", [-1, float("nan"), float("inf"), None, True])
def test_internal_weight_cannot_invert_evidence_contract(weight):
    engine = DecisionEngine()
    engine.add_rule(SeeingRule())
    with pytest.raises(ValueError, match="finite and non-negative"):
        engine.evaluate(context(None, 1), {"decision_weights": {"seeing": weight}})
