from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot import extended_catalogue as catalog


def search(query="", **kwargs):
    return catalog.search_catalogue(profile={}, equipment_id="samyang_183", query=query, **kwargs)


def test_pinned_complete_sources_and_exclusions_reconcile():
    records, stats, manifest = catalog._load()
    assert stats["records"] == 13382
    assert stats["openngc_records"] + stats["additional_imaging_regions"] == len(records)
    assert stats["openngc_records"] + stats["excluded_duplicates"] + stats["excluded_nonexistent"] == stats["openngc_source_rows"] == 14034
    assert stats["messier_designations"] == 110
    assert len({item["id"] for item in records}) == len(records)
    assert not any(item["source_type"] in {"Dup", "NonEx"} for item in records)
    assert all(item["source_url"].startswith("https://") for item in records)
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((catalog.DATA / name).read_bytes()).hexdigest() == digest
    assert manifest["license"] == "CC-BY-SA-4.0"
    attributes = (Path(__file__).parents[2] / ".gitattributes").read_text()
    assert "astropilot/catalogue_data/* -text" in attributes


@pytest.mark.parametrize("query,expected", [("M31", "NGC0224"), ("NGC 224", "NGC0224"),
    ("M001", "NGC1952"), ("Andromède", "NGC0224"), ("M45", "Mel022"), ("M40", "M040")])
def test_normalised_identifiers_and_french_names_resolve_without_false_number_priority(query, expected):
    assert search(query)["results"][0]["catalogue_id"] == expected


def test_small_component_is_not_substituted_for_a_whole_region_or_reflection_halo():
    entries = search("IC1396")["results"]
    assert len(entries) == 2
    component = next(item for item in entries if item["source_id"] == "openngc")
    region = next(item for item in entries if item["source_id"] != "openngc")
    assert component["major_arcmin"] == 14
    assert region["major_arcmin"] == 170
    assert component["framing"]["status"] == "small_in_field"
    assert region["framing"]["status"] == "nominal_fit"
    pleiades = search("M45")["results"][0]
    assert pleiades["kind"] == "open_cluster"
    assert pleiades["curated_notes"][0]["extent_arcmin"] is None


def test_uncertain_messier_identification_is_explicitly_sourced_and_not_silently_merged():
    m102 = search("M102")["results"][0]
    assert m102["catalogue_id"] == "NGC5866"
    assert m102["identity_notes"][0]["sources"]
    assert "discutée" in m102["identity_notes"][0]["text"]
    assert search("M101")["results"][0]["id"] != m102["id"]


def test_missing_measurements_unknown_types_and_no_filter_or_exposure_guess():
    double = search("M40")["results"][0]
    assert double["kind"] == "double_star"
    assert double["extent_arcmin"] is None and double["framing"]["status"] == "unknown"
    galaxy = search("M51")["results"][0]
    assert galaxy["framing"]["status"] == "small_in_field"
    assert not galaxy["mission_enabled_by_catalogue"]
    assert not {"target_hours", "filter_profile_id", "mission", "decision_id"} & galaxy.keys()


def test_infrared_fallback_diameters_do_not_certify_a_visible_light_framing():
    galaxy = search("NGC0094")["results"][0]
    assert galaxy["major_arcmin"] is not None
    assert galaxy["extent_bound"] == "scope_unverified"
    assert galaxy["framing"]["status"] == "unknown"
    assert "2MASS" in galaxy["dimension_note"]
    cluster = search("M45")["results"][0]
    assert "zone centrale" in cluster["dimension_note"]


def test_pagination_and_framing_filters_return_bounded_coherent_results():
    first, second = search(limit=25), search(limit=25, offset=25)
    assert len(first["results"]) == len(second["results"]) == 25
    assert not {x["id"] for x in first["results"]} & {x["id"] for x in second["results"]}
    assert search(offset=100000)["results"] == []
    for status in ("nominal_fit", "small_in_field", "requires_framing_check", "unknown"):
        result = search(kind="hii_region", framing=status)
        assert all(item["kind"] == "hii_region" and item["framing"]["status"] == status for item in result["results"])


def test_response_edits_do_not_mutate_cached_records_or_user_progress():
    profile = {"projects": {"Sh2-129": {"hours": 7}}, "sessions": [{"id": "saved"}]}
    before = deepcopy(profile)
    result = catalog.search_catalogue(profile=profile, equipment_id="samyang_183", query="M31")
    result["results"][0]["aliases"].append("changed")
    result["catalogue"]["by_kind"]["galaxy"] = -1
    assert "changed" not in search("M31")["results"][0]["aliases"]
    assert search()["catalogue"]["by_kind"]["galaxy"] > 0
    assert profile == before


@pytest.mark.parametrize("text,ra", [("-01:00:00", True), ("24:00:00", True),
    ("-00:30:00", True), ("12:60:00", True), ("+90:01:00", False), ("nan:00:00", False), ("", True)])
def test_invalid_coordinates_remain_unknown(text, ra):
    assert catalog._coordinate(text, ra=ra) is None


def test_southern_sign_at_zero_degrees_is_preserved():
    assert catalog._coordinate("-00:30:00", ra=False) == -.5


def test_api_is_offline_read_only_and_validates_query_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    profile = {"active_equipment": "samyang_183"}
    def no_weather(*args): pytest.fail("Reference search must never call weather")
    client = TestClient(create_app(profile_provider=lambda: profile, weather_provider=no_weather))
    response = client.get("/v1/target-catalogue/search?q=M31&limit=1")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert len(response.json()["results"]) == 1
    for query in ("limit=101", "offset=-1", "kind=unclassified-fiction", "framing=guaranteed", "q=" + "a" * 121, "equipment=missing"):
        assert client.get("/v1/target-catalogue/search?" + query).status_code == 422
    assert client.get("/catalogue").status_code == 200
    assert "CC BY-SA" in client.get("/ui/catalogue-license.txt").text or "Attribution-ShareAlike" in client.get("/ui/catalogue-license.txt").text
    assert not list(tmp_path.rglob("*.json"))


def test_reference_catalogue_remains_browsable_before_equipment_configuration():
    client = TestClient(create_app(profile_provider=lambda: {}))
    response = client.get("/v1/target-catalogue/search?q=M31")
    assert response.status_code == 200
    assert response.json()["geometry"]["status"] == "unknown"
    assert response.json()["results"][0]["framing"]["status"] == "unknown"


def test_corrupt_source_fails_closed_instead_of_returning_partial_data(tmp_path, monkeypatch):
    manifest = {"files": {"NGC.csv": "incorrect"}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "NGC.csv").write_text("not the pinned catalogue")
    catalog._load.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(catalog, "DATA", tmp_path)
            client = TestClient(create_app(profile_provider=lambda: {"active_equipment": "samyang_183"}))
            response = client.get("/v1/target-catalogue/search")
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "catalogue_unavailable"
    finally:
        catalog._load.cache_clear()


def test_catalogue_ui_ignores_late_results_and_restarts_pagination_when_filters_change():
    node = shutil.which("node")
    if not node: pytest.skip("Node required for executable UI regression")
    source = (Path(__file__).parents[2] / "astropilot/web/catalogue.js").read_text().split('node("#catalogue-search").addEventListener', 1)[0]
    harness = r'''
const assert=require('node:assert/strict');
const elements={}, shown=[], pending=[];
const document={querySelector:s=>elements[s] ||= {value:'',disabled:false,textContent:'',replaceChildren(){}}};
const location={search:''},window={};
async function fetch(url){return new Promise(resolve=>pending.push({url,resolve}));}
''' + source + r'''
showCatalogue=payload=>shown.push(payload);
(async()=>{
 const first=loadCatalogue();elements['#catalogue-query'].value='M31';const second=loadCatalogue();
 pending[1].resolve({ok:true,json:async()=>({total:1,results:[{catalogue_id:'NGC0224'}]})});await second;
 pending[0].resolve({ok:true,json:async()=>({total:100,results:[{catalogue_id:'late'}]})});await first;
 assert.equal(shown.length,1);assert.equal(shown[0].results[0].catalogue_id,'NGC0224');
 elements['#catalogue-query'].value='M42';const next=loadCatalogue(25);
 assert.equal(new URL('http://local'+pending[2].url).searchParams.get('offset'),'0');
 pending[2].resolve({ok:true,json:async()=>({total:1,results:[]})});await next;
 window.NIGHTMERIT_OFFLINE_CATALOGUE={results:[{catalogue_id:'M010',aliases:['M10'],search_text:'m10',kind:'galaxy',framing:{status:'small_in_field'}},{catalogue_id:'M001',aliases:['M1'],search_text:'m1',kind:'nebula',framing:{status:'nominal_fit'}}]};
 const local=offlineCataloguePage(new URLSearchParams({q:'M1',offset:0,limit:25}));
 assert.equal(local.results[0].catalogue_id,'M001');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", harness], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_production_first_run_catalogue_does_not_require_or_create_a_profile(tmp_path, monkeypatch):
    """Use the real default provider, as the packaged app does on a clean Mac."""
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    def no_weather(*args):
        pytest.fail('First-run reference lookup must not call weather')
    client = TestClient(create_app(weather_provider=no_weather))
    assert not client.get('/v1/configuration').json()['configured']
    response = client.get('/v1/target-catalogue/search?q=M31&limit=1')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['results'][0]['catalogue_id'] == 'NGC0224'
    assert payload['geometry']['status'] == 'unknown'
    assert payload['equipment_id'] is None
    assert payload['catalogue']['records'] == 13382
    response = client.get('/v1/target-catalogue/search?q=IC1396&equipment=samyang_183')
    assert response.status_code == 200, response.text
    assert {r['major_arcmin'] for r in response.json()['results']} == {14, 170}
    assert client.get('/v1/target-catalogue?equipment=samyang_183').status_code == 200
    assert client.get('/v1/target-catalogue').status_code == 422  # no setup guessed
    assert not client.get('/v1/configuration').json()['configured']
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('contents', [b'{broken json', b'{"projects":{}}', b'\xff\xfe'])
def test_production_invalid_profile_is_not_silently_treated_as_first_run(tmp_path, monkeypatch, contents):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    path = tmp_path / 'user_profile.json'
    path.write_bytes(contents)
    client = TestClient(create_app())
    for route in ['/v1/target-catalogue/search?q=M31', '/v1/target-catalogue?equipment=samyang_183']:
        response = client.get(route)
        assert response.status_code == 503, response.text
        assert response.json()['detail']['code'] == 'catalogue_unavailable'
        assert str(tmp_path) not in response.text
    assert path.read_bytes() == contents
    assert list(tmp_path.iterdir()) == [path]


def test_injected_missing_provider_failure_is_not_masked(tmp_path, monkeypatch):
    from astropilot.user_profile import UserProfileError
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    def failing_provider():
        try:
            (tmp_path / 'user_profile.json').read_text()
        except FileNotFoundError as cause:
            raise UserProfileError('injected failure') from cause
    client = TestClient(create_app(profile_provider=failing_provider))
    response = client.get('/v1/target-catalogue/search?q=M31')
    assert response.status_code == 503
    assert not list(tmp_path.iterdir())
