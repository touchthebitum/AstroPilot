from pathlib import Path

from fastapi.testclient import TestClient

from astropilot.app import create_app


class UnusedService:
    def evaluate(self, **kwargs):
        raise AssertionError("the UI shell must not evaluate a decision")


def make_client():
    return TestClient(
        create_app(
            service_factory=lambda: UnusedService(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=lambda: {},
        )
    )


def test_root_serves_tonight_classic_ui():
    response = make_client().get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Ce soir — AstroPilot" in response.text
    assert "Voir ma mission" in response.text
    assert 'src="/ui/app.js"' in response.text


def test_tonight_ui_assets_are_served():
    client = make_client()

    stylesheet = client.get("/ui/styles.css")
    script = client.get("/ui/app.js")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert "fetch(\"/v1/tonight\"" in script.text
    assert "currentDecision" in script.text


def test_web_assets_are_declared_as_package_data():
    project = Path(__file__).parents[2]
    pyproject = (project / "pyproject.toml").read_text()

    assert '"web/*"' in pyproject
