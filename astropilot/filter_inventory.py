"""User-declared filter wheel inventory. No hardware access or optical inference."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from decision.definitions.production_filter_optical_profiles import FILTER_OPTICAL_PROFILES


def filter_references():
    return [{"id":p.filter_profile_id,"label":"Baader "+p.filter_type+" Highspeed (6.5 nm)","filter_type":p.filter_type,"bandwidth_nm":p.fwhm_nm} for p in FILTER_OPTICAL_PROFILES]

class FilterSlot(BaseModel):
    model_config=ConfigDict(extra="forbid", frozen=True)
    position: int=Field(ge=1,le=20,strict=True)
    label: str=Field(min_length=1,max_length=120)
    filter_type: Literal["Ha","OIII","SII","L","R","G","B","dual_band","other"]
    filter_profile_id: str|None=None
    bandwidth_nm: float|None=Field(default=None,gt=0,le=1000,allow_inf_nan=False)

    @model_validator(mode="after")
    def exact_reference(self):
        if not self.label.strip(): raise ValueError("filter_label_required")
        if self.filter_profile_id is not None:
            ref=next((p for p in FILTER_OPTICAL_PROFILES if p.filter_profile_id==self.filter_profile_id),None)
            if ref is None or ref.filter_type!=self.filter_type or self.bandwidth_nm!=ref.fwhm_nm:
                raise ValueError("filter_reference_mismatch")
        return self

class FilterInventory(BaseModel):
    model_config=ConfigDict(extra="forbid", frozen=True)
    wheel_name: str=Field(min_length=1,max_length=120)
    slot_count: int=Field(ge=1,le=20,strict=True)
    slots: list[FilterSlot]=Field(max_length=20)

    @model_validator(mode="after")
    def unique_positions(self):
        if not self.wheel_name.strip(): raise ValueError("wheel_name_required")
        positions=[x.position for x in self.slots]
        if len(set(positions))!=len(positions) or any(x>self.slot_count for x in positions):
            raise ValueError("wheel_slot_invalid")
        return self

class FilterInventoryWrite(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_revision: int=Field(ge=0,strict=True)
    equipment_id: str=Field(min_length=1,max_length=120)
    inventory: FilterInventory


def declared_filter_ids(profile,equipment_id):
    inventories=profile.get("filter_inventories",{})
    if equipment_id not in inventories: return None  # Legacy manual confirmation remains valid.
    return {s["filter_profile_id"] for s in inventories[equipment_id]["slots"] if s.get("filter_profile_id")}


def inventory_mounting(inventory):
    name = inventory.get("wheel_name")
    return "single" if name == "Filtre monté seul" else "none" if name == "Aucun filtre" else "wheel"
