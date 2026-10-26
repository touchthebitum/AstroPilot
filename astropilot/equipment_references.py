"""Offline manufacturer references; deliberately independent of mission capabilities.

Listing a component never registers ownership or makes a setup eligible for a mission.
Only complete, explicitly identified variants can be copied into the custom editor.
"""
from datetime import date
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class ReferenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: str = Field(min_length=1)
    url: str
    checked_on: date

    @model_validator(mode="after")
    def manufacturer_only(self):
        url = urlsplit(self.url)
        if (url.scheme != "https" or url.username or url.password or url.port
                or url.hostname not in {"www.skywatcherusa.com", "www.sharpstar-optics.com",
                                       "us.zwoastro.com", "www.zwoastro.com", "i.zwoastro.com",
                                       "www.astronomik.com", "www.baader-planetarium.com"}):
            raise ValueError("Expected an HTTPS manufacturer source")
        return self


class ReferenceSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    focal_length_mm: float | None = Field(default=None, gt=0, strict=True)
    aperture_mm: float | None = Field(default=None, gt=0, strict=True)
    f_ratio: float | None = Field(default=None, gt=0, strict=True)
    pixel_size_um: float | None = Field(default=None, gt=0, strict=True)
    sensor_width_px: StrictInt | None = Field(default=None, gt=0, strict=True)
    sensor_height_px: StrictInt | None = Field(default=None, gt=0, strict=True)
    monochrome: StrictBool | None = None
    filter_type: str | None = None
    format: str | None = None
    fwhm_nm: float | None = Field(default=None, gt=0, strict=True)


COMPONENT_FIELDS = {
    "optics": {"focal_length_mm", "aperture_mm", "f_ratio"},
    "camera": {"pixel_size_um", "sensor_width_px", "sensor_height_px", "monochrome"},
    "filter": {"filter_type", "format", "fwhm_nm"},
}


class EquipmentReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    category: Literal["optics", "camera", "filter"]
    manufacturer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    aliases: list[str]
    specs: ReferenceSpecs
    notes: str = Field(min_length=1)
    source: ReferenceSource
    mission_compatibility: Literal["not_verified"] = "not_verified"

    @model_validator(mode="after")
    def component_fields_only(self):
        domains = {"Askar": {"www.sharpstar-optics.com"}, "Sky-Watcher": {"www.skywatcherusa.com"},
                   "ZWO": {"us.zwoastro.com", "www.zwoastro.com", "i.zwoastro.com"},
                   "Astronomik": {"www.astronomik.com"}, "Baader": {"www.baader-planetarium.com"}}
        if urlsplit(self.source.url).hostname not in domains.get(self.manufacturer, set()):
            raise ValueError("Source does not belong to this manufacturer")
        present = set(self.specs.model_dump(exclude_none=True))
        if not present <= COMPONENT_FIELDS[self.category]:
            raise ValueError("Specifications belong to a different component category")
        return self

    @property
    def can_copy(self) -> bool:
        return self.category != "filter" and COMPONENT_FIELDS[self.category] <= set(
            self.specs.model_dump(exclude_none=True))


class EquipmentReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    entries: list[EquipmentReference]

    @model_validator(mode="after")
    def unique_ids(self):
        if len({entry.id for entry in self.entries}) != len(self.entries):
            raise ValueError("Duplicate equipment reference ID")
        return self


def equipment_references() -> dict:
    path = Path(__file__).with_name("catalogue_data") / "equipment_references_v1.json"
    catalogue = EquipmentReferences.model_validate(json.loads(path.read_text(encoding="utf-8")))
    result = catalogue.model_dump(mode="json", exclude_none=True)
    for entry, projected in zip(catalogue.entries, result["entries"]):
        projected["can_copy"] = entry.can_copy
    return result
