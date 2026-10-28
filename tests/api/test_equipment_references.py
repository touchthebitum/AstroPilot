"""A reference is evidence for identification, never a mission capability."""
import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from astropilot.equipment_references import EquipmentReferences, equipment_references

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "astropilot/catalogue_data/equipment_references_v1.json"


def catalogue():
    return json.loads(DATA.read_text())


def test_variants_sources_and_incomplete_references():
    result = equipment_references()
    entries = {entry["id"]: entry for entry in result["entries"]}
    assert len(entries) == 22
    native = entries["skywatcher_quattro_150_native"]
    reduced = entries["skywatcher_quattro_150_reduced"]
    assert native["specs"]["focal_length_mm"] == 600
    assert reduced["specs"]["focal_length_mm"] == 518
    assert "Newton" in native["aliases"]
    assert native["can_copy"] and reduced["can_copy"]
    ambiguous = entries["skywatcher_quattro_200"]
    assert not ambiguous["can_copy"]
    assert "aperture_mm" not in ambiguous["specs"]
    assert entries["zwo_asi183mm_pro"]["specs"]["monochrome"] is True
    assert entries["zwo_asi183mc_pro"]["specs"]["monochrome"] is False
    assert "P25" in entries["zwo_asi2600mm_pro_p25"]["model"]
    for entry in entries.values():
        assert entry["mission_compatibility"] == "not_verified"
        assert entry["source"]["checked_on"] == "2026-10-26"
        if entry["category"] == "filter":
            assert not entry["can_copy"]
            assert "filter_profile_id" not in entry
        if entry["manufacturer"] == "Astronomik":
            assert "fwhm_nm" not in entry["specs"]


@pytest.mark.parametrize("change", [
    lambda data: data["entries"].append(copy.deepcopy(data["entries"][0])),
    lambda data: data["entries"][0]["specs"].update(focal_length_mm=0),
    lambda data: data["entries"][0]["specs"].update(focal_length_mm=float("nan")),
    lambda data: data["entries"][0]["specs"].update(focal_length_mm=True),
    lambda data: data["entries"][0]["specs"].update(focal_length_mm="300"),
    lambda data: data["entries"][0]["specs"].update(monochrome=True),
    lambda data: data["entries"][0]["source"].update(url="javascript:alert(1)"),
    lambda data: data["entries"][0]["source"].update(url="https://www.sharpstar-optics.com.evil.test/"),
    lambda data: data["entries"][0]["source"].update(url="https://www.zwoastro.com/product/asi6200/"),
    lambda data: data["entries"][0].update(mission_compatibility="verified"),
    lambda data: data["entries"][0].pop("source"),
])
def test_invalid_catalogue_fails_closed(change):
    data = catalogue()
    change(data)
    with pytest.raises(ValidationError):
        EquipmentReferences.model_validate(data)


def test_get_is_offline_and_preserves_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    marker = tmp_path / "personal-do-not-touch.json"
    marker.write_bytes(b'{"preserved":true}\n')
    (tmp_path / "user_profile.json").write_bytes((ROOT / "data/user_profile.json").read_bytes())
    from astropilot.app import create_app
    client = TestClient(create_app())
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    response = client.get("/v1/equipment-references")
    assert response.status_code == 200
    assert response.json() == equipment_references()
    assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert client.post("/v1/equipment-references", json={}).status_code == 405


def test_unavailable_catalogue_is_not_an_empty_success(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    import astropilot.equipment_references as references
    from astropilot.app import create_app
    def unavailable():
        raise ValueError("invalid reference")
    monkeypatch.setattr(references, "equipment_references", unavailable)
    result = TestClient(create_app()).get("/v1/equipment-references")
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "equipment_references_unavailable"


def test_packaged_reference_data_is_included_for_both_platforms():
    for name in ("AstroPilot.spec", "AstroPilot-windows.spec"):
        assert '"astropilot/catalogue_data"' in (ROOT / name).read_text()
        assert '.glob("*")' in (ROOT / name).read_text()
    assert '"catalogue_data/*"' in (ROOT / "pyproject.toml").read_text()
