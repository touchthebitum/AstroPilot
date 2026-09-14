from fastapi.testclient import TestClient

from astropilot.app import create_app


def test_runtime_identity_is_exact_and_non_sensitive(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    response = TestClient(create_app()).get("/v1/runtime-identity")

    assert response.status_code == 200
    assert response.json() == {"application": "astropilot"}
    assert "version" not in response.json()
    assert str(tmp_path) not in response.text
    assert list(tmp_path.iterdir()) == []


def test_runtime_identity_does_not_resolve_application_state():
    def unexpected_call(*args, **kwargs):
        raise AssertionError("runtime identity must not resolve application state")

    client = TestClient(
        create_app(
            service_factory=unexpected_call,
            weather_provider=unexpected_call,
            profile_provider=unexpected_call,
        )
    )

    assert client.get("/v1/runtime-identity").json() == {
        "application": "astropilot"
    }
