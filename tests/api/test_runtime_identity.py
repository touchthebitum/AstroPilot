import pytest
from fastapi.testclient import TestClient

import astropilot.app as app_module
from astropilot.app import create_app, runtime_identity_payload


def test_runtime_identity_is_exact_and_non_sensitive(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASTROPILOT_BUILD_COMMIT", "8541acc")
    response = TestClient(create_app()).get("/v1/runtime-identity")

    assert response.status_code == 200
    assert response.json() == {
        "application": "astropilot",
        "version": "1.0.0b5",
        "build": "8541acc",
        "architecture": response.json()["architecture"],
    }
    assert response.json()["architecture"]
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

    identity = client.get("/v1/runtime-identity").json()

    assert identity["application"] == "astropilot"
    assert identity["version"] == "1.0.0b5"
    assert identity["build"]
    assert identity["architecture"]


def test_runtime_identity_has_controlled_development_build_fallback(monkeypatch):
    monkeypatch.delenv("ASTROPILOT_BUILD_COMMIT", raising=False)

    identity = TestClient(create_app()).get("/v1/runtime-identity").json()

    assert identity["version"] == "1.0.0b5"
    assert identity["build"] == "development"


@pytest.mark.parametrize(
    ("reported", "expected"),
    (
        ("AMD64", "x86_64"),
        ("x86_64", "x86_64"),
        ("arm64", "arm64"),
        ("riscv64-test", "riscv64-test"),
    ),
)
def test_runtime_architecture_is_canonical_and_unknown_values_pass_through(
    monkeypatch,
    reported,
    expected,
):
    monkeypatch.setattr(app_module.platform, "machine", lambda: reported)

    assert runtime_identity_payload()["architecture"] == expected
