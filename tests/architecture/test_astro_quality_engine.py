import pytest

from decision.quality.astro_quality_context import AstroQualityContext
from decision.quality.astro_quality_engine import AstroQualityEngine


def test_aqi_rewards_excellent_imaging_conditions():
    context = AstroQualityContext(
        target_altitude_deg=75.0,
        cloud_cover_percent=0.0,
        moon_penalty=0.0,
        seeing_arcsec=1.2,
        image_quality_score=9.0,
    )

    result = AstroQualityEngine.evaluate(context)

    assert result.score >= 95
    assert result.confidence == 1.0
    assert result.limiting_factor == "setup"


def test_aqi_clouds_can_be_the_limiting_factor():
    context = AstroQualityContext(
        target_altitude_deg=70.0,
        cloud_cover_percent=80.0,
        moon_penalty=0.1,
        seeing_arcsec=1.5,
        image_quality_score=9.0,
    )

    result = AstroQualityEngine.evaluate(context)

    assert result.metrics["cloud_score"] == 20.0
    assert result.limiting_factor == "clouds"
    assert result.score < 80


def test_aqi_handles_missing_optional_quality_inputs():
    context = AstroQualityContext(
        target_altitude_deg=65.0,
        cloud_cover_percent=10.0,
        moon_penalty=0.2,
        seeing_arcsec=None,
        image_quality_score=None,
    )

    result = AstroQualityEngine.evaluate(context)

    assert 0 <= result.score <= 100
    assert result.confidence == 0.6
    assert "seeing_score" not in result.metrics
    assert "setup_score" not in result.metrics

@pytest.mark.parametrize(
    ("context", "minimum", "maximum"),
    [
        (
            AstroQualityContext(
                target_altitude_deg=75,
                cloud_cover_percent=0,
                moon_penalty=0.0,
                seeing_arcsec=1.2,
                image_quality_score=9.0,
            ),
            95,
            100,
        ),
        (
            AstroQualityContext(
                target_altitude_deg=60,
                cloud_cover_percent=15,
                moon_penalty=0.2,
                seeing_arcsec=1.7,
                image_quality_score=8.0,
            ),
            80,
            90,
        ),
        (
            AstroQualityContext(
                target_altitude_deg=42,
                cloud_cover_percent=35,
                moon_penalty=0.5,
                seeing_arcsec=2.4,
                image_quality_score=7.0,
            ),
            50,
            70,
        ),
        (
            AstroQualityContext(
                target_altitude_deg=25,
                cloud_cover_percent=75,
                moon_penalty=0.8,
                seeing_arcsec=3.5,
                image_quality_score=6.0,
            ),
            0,
            40,
        ),
    ],
)
def test_aqi_preserves_expected_quality_bands(
        context,
        minimum,
        maximum,
    ):
        result = AstroQualityEngine.evaluate(context)

        assert minimum <= result.score <= maximum
