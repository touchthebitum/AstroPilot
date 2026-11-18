import requests
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.location_search import find_locations


def test_search_is_read_only_and_validates_provider_coordinates(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path / "profile"))
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [{"name": "Buttes", "admin1": "Neuchâtel", "country": "Suisse", "latitude": 46.8883, "longitude": 6.5525}, {"name": "invalid", "latitude": 999, "longitude": 6}, {"name": "invalid", "latitude": True, "longitude": 6}]}
    def get(url, **kwargs):
        calls.append((url, kwargs)); return Response()
    monkeypatch.setattr("astropilot.location_search.requests.get", get)
    client = TestClient(create_app())
    result = client.get("/v1/locations", params={"name": "Buttes"})
    assert result.status_code == 200
    assert result.json()["results"] == [{"label": "Buttes — Neuchâtel — Suisse", "latitude": 46.8883, "longitude": 6.5525}]
    assert calls[0][1]["timeout"] == 10
    assert not list(tmp_path.rglob("user_profile.json"))
    assert client.get("/v1/locations?name=x").status_code == 422


def test_search_failure_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path / "profile"))
    def fail(*args, **kwargs): raise requests.Timeout()
    monkeypatch.setattr("astropilot.location_search.requests.get", fail)
    result = TestClient(create_app()).get("/v1/locations?name=Buttes")
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "location_search_unavailable"
