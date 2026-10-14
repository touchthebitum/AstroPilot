from datetime import datetime, timedelta, timezone
import pytest
import astro_score
from decision.filtering.authorized_selected_filter import authorized_selected_filter
from decision.validation.decision_consistency import DecisionConsistencyError


def authority(intent):
    start=datetime(2026,10,16,3,tzinfo=timezone.utc)
    profile={'active_equipment':'samyang_183','projects':{'Sh2-129':{
        'imaging_field_id':'sh2-129_ou4',
        'acquisition_intent_targets':[{'acquisition_intent_id':intent,'target_hours':6}],
        'acquisition_intent_progress':[{'acquisition_intent_id':intent,'acquired_duration_manual':0}]}}}
    value=astro_score.build_mission_input({'catalog_key':'Sh2-129',
        'selected_acquisition_intent_id':intent,'window':{'start':start,'end':start+timedelta(hours=2)}},profile=profile)
    assert value.selected_filter is None
    return value.creation_authorization


@pytest.mark.parametrize('intent,kind',[('sh2-129_ha','Ha'),('ou4_oiii','OIII')])
def test_authorized_profile_without_legacy_inventory(intent,kind,monkeypatch):
    monkeypatch.setattr(astro_score.FilterInventoryLoader,'load',lambda:pytest.fail('Legacy inventory read'))
    selected=authorized_selected_filter(authority(intent))
    assert selected.filter_type==kind
    assert selected.bandwidth_nm==6.5
    assert selected.source=='authorized_optical_profile'


@pytest.mark.parametrize('value',[None,object()])
def test_description_requires_real_modern_authority(value):
    with pytest.raises(DecisionConsistencyError):authorized_selected_filter(value)
