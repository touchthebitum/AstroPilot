from decision.quality.astro_quality_context import AstroQualityContext
from decision.quality.astro_quality_result import AstroQualityResult


def test_astro_quality_context_preserves_aqi_inputs():
    context = AstroQualityContext(
        target_altitude_deg=65.0,
        cloud_cover_percent=10.0,
        moon_penalty=0.2,
        seeing_arcsec=1.5,
        image_quality_score=8.5,
    )

    assert context.target_altitude_deg == 65.0
    assert context.cloud_cover_percent == 10.0
    assert context.moon_penalty == 0.2
    assert context.seeing_arcsec == 1.5
    assert context.image_quality_score == 8.5


def test_astro_quality_result_is_explicitly_zero_to_hundred_scale():
    result = AstroQualityResult(
        score=87.0,
        confidence=0.9,
        limiting_factor="clouds",
        metrics={
            "cloud_score": 90.0,
        },
    )

    assert result.score == 87.0
    assert result.confidence == 0.9
    assert result.limiting_factor == "clouds"