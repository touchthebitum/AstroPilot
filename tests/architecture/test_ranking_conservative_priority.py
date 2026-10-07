from conftest import modern_ranking_project
"""Ranking contract: missing preference contributes no reward and cannot soften risk."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
import astro_score as a
from decision.models.future_opportunity import FutureOpportunity

@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setattr(a,'future_engine',SimpleNamespace(estimate=lambda *args,**kw:FutureOpportunity(20,'FAIBLE',.5,2,10)))
    profile={'location':{'latitude':46.7508,'longitude':6.5495},'active_equipment':'samyang_183','preferences':{},'projects':{'M31':modern_ranking_project({'hours':0,'target_hours':20,'importance':5})}}
    def candidate(p=profile):return a.recommend_project_for_night([{'name':'M31','catalog_key':'M31','global_score':80}],available_hours=2,profile=p)[0]
    return profile,candidate

@pytest.mark.parametrize('offset',[-20,-.001,0,.001,20])
def test_cap_continuous_formula_at_threshold(monkeypatch,fixture,offset):
    _,candidate=fixture
    monkeypatch.setattr(a,'portfolio_candidate_bonus',lambda **kw:28+offset)
    c=candidate();assert c.final_score==pytest.approx(56+28+offset-.6-.3*max(0,offset))

@pytest.mark.parametrize('component',['project_part','roi_bonus','closure_bonus','marginal_progress_bonus','opportunity_bonus','diversity_bonus'])
def test_removing_positive_component_cannot_raise_final_score(monkeypatch,fixture,component):
    _,candidate=fixture
    keys=['project_part','roi_bonus','closure_bonus','marginal_progress_bonus','opportunity_bonus','diversity_bonus']
    contributions={k:0 for k in keys};contributions['project_part']=28
    original=a.portfolio_candidate_bonus
    monkeypatch.setattr(a,'portfolio_candidate_bonus',lambda **kw:original(**contributions))
    before=candidate().final_score;contributions[component]+=.01
    assert candidate().final_score>=before

@pytest.mark.parametrize('mode',['roi','completion','diversification','risk'])
def test_absent_importance_does_not_beat_positive_with_critical_risk(monkeypatch,fixture,mode):
    profile,_=fixture;profile['preferences']['decision_mode']=mode
    monkeypatch.setattr(a,'future_engine',SimpleNamespace(estimate=lambda *args,**kw:FutureOpportunity(0,'CRITIQUE',.5,2,0)))
    def score(p):return a.recommend_project_for_night([{'name':'M31','catalog_key':'M31','global_score':40}],available_hours=2,profile=p)[0].decision_score
    known=deepcopy(profile);known['projects']['M31']['importance']=1
    absent=deepcopy(profile);absent['projects']['M31'].pop('importance')
    assert score(absent)<=score(known)

@pytest.mark.parametrize('astro',[20,40,60])
@pytest.mark.parametrize('mode',['roi','completion','diversification','risk'])
def test_twelve_adverse_risk_winners(monkeypatch, fixture, astro, mode):
    profile, _ = fixture
    profile['preferences']['decision_mode'] = mode
    profile['projects'] = {
        'M31': modern_ranking_project({'hours': 0, 'target_hours': 20}),
        'M33': modern_ranking_project({'hours': 0, 'target_hours': 20, 'importance': 1}),
    }
    monkeypatch.setattr(a, 'future_engine', SimpleNamespace(
        estimate=lambda *args, **kw: FutureOpportunity(0, 'CRITIQUE', .5, 2, 0)))
    candidates = a.recommend_project_for_night([
        {'name': name, 'catalog_key': name, 'global_score': astro}
        for name in profile['projects']
    ], available_hours=2, profile=profile)
    by_name = {c.name: c for c in candidates}
    from decision.opportunity.opportunity_engine import OpportunityEngine
    assert OpportunityEngine().evaluate(candidates=candidates).candidate.name == 'M33'
    assert by_name['M31'].decision_score <= by_name['M33'].decision_score
    assert by_name['M31'].final_score <= by_name['M33'].final_score
    assert by_name['M31'].priority is None
    assert by_name['M33'].priority == 10

@pytest.mark.parametrize('mode',['balanced','roi','completion','diversification','risk'])
@pytest.mark.parametrize('importance',[0,1,2,5,10])
@pytest.mark.parametrize('astro',[20,40,60,70,80])
@pytest.mark.parametrize('risk',['CRITIQUE','ÉLEVÉ','INCONNU'])
def test_removing_importance_never_increases_scores(monkeypatch, fixture, mode, importance, astro, risk):
    profile, _ = fixture
    profile['preferences']['decision_mode'] = mode
    monkeypatch.setattr(a, 'future_engine', SimpleNamespace(
        estimate=lambda *args, **kw: FutureOpportunity(0, risk, .5, 2, 0)))
    def score(p):
        return a.recommend_project_for_night([
            {'name':'M31','catalog_key':'M31','global_score':astro}
        ], available_hours=2, profile=p)[0]
    known = deepcopy(profile)
    known['projects']['M31']['importance'] = importance
    absent = deepcopy(known)
    absent['projects']['M31'].pop('importance')
    before, after = score(known), score(absent)
    assert after.final_score <= before.final_score
    assert after.decision_score <= before.decision_score
    assert after.priority is None
    assert before.priority == importance * 10
    assert after.portfolio_score <= before.portfolio_score

@pytest.mark.parametrize('astro',[40,80])
def test_unknown_opportunity_has_no_bonus(monkeypatch, fixture, astro):
    profile, _ = fixture
    captured = []
    original = a.portfolio_candidate_bonus
    def observe(**kw):
        captured.append(kw)
        return original(**kw)
    monkeypatch.setattr(a, 'portfolio_candidate_bonus', observe)
    monkeypatch.setattr(a, 'future_engine', SimpleNamespace(
        estimate=lambda *args, **kw: FutureOpportunity(0, 'INCONNU', 0, 0, 0)))
    a.recommend_project_for_night([
        {'name':'M31','catalog_key':'M31','global_score':astro}
    ], available_hours=2, profile=profile)
    assert captured[0]['opportunity_bonus'] == 0


pytestmark = pytest.mark.usefixtures("selected_modern_ranking_intent")
