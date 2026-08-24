from decision.quality.astro_quality_result import AstroQualityResult


class AstroQualityEngine:
    WEIGHTS = {
        "altitude": 0.20,
        "clouds": 0.30,
        "moon": 0.15,
        "seeing": 0.20,
        "setup": 0.15,
    }

    @staticmethod
    def _altitude_score(altitude: float) -> float:
        if altitude >= 70:
            return 100.0

        if altitude >= 50:
            return 70.0 + (
                (altitude - 50.0)
                / 20.0
                * 30.0
            )

        if altitude >= 30:
            return 40.0 + (
                (altitude - 30.0)
                / 20.0
                * 30.0
            )

        return 20.0

    @staticmethod
    def _cloud_score(cloud_cover: float) -> float:
        return max(
            0.0,
            min(100.0, 100.0 - cloud_cover),
        )

    @staticmethod
    def _moon_score(moon_penalty: float) -> float:
        penalty = max(
            0.0,
            min(1.0, moon_penalty),
        )

        return (1.0 - penalty) * 100.0

    @staticmethod
    def _seeing_score(seeing: float) -> float:
        if seeing <= 1.2:
            return 100.0
        if seeing <= 1.8:
            return 90.0
        if seeing <= 2.3:
            return 75.0
        if seeing <= 3.0:
            return 55.0
        return 30.0

    @staticmethod
    def evaluate(context) -> AstroQualityResult:
        metrics = {
            "altitude_score": (
                AstroQualityEngine._altitude_score(
                    context.target_altitude_deg
                )
            ),
            "cloud_score": (
                AstroQualityEngine._cloud_score(
                    context.cloud_cover_percent
                )
            ),
            "moon_score": (
                AstroQualityEngine._moon_score(
                    context.moon_penalty
                )
            ),
        }

        weighted_scores = [
            (
                metrics["altitude_score"],
                AstroQualityEngine.WEIGHTS["altitude"],
                "altitude",
            ),
            (
                metrics["cloud_score"],
                AstroQualityEngine.WEIGHTS["clouds"],
                "clouds",
            ),
            (
                metrics["moon_score"],
                AstroQualityEngine.WEIGHTS["moon"],
                "moon",
            ),
        ]

        if context.seeing_arcsec is not None:
            metrics["seeing_score"] = (
                AstroQualityEngine._seeing_score(
                    context.seeing_arcsec
                )
            )

            weighted_scores.append(
                (
                    metrics["seeing_score"],
                    AstroQualityEngine.WEIGHTS["seeing"],
                    "seeing",
                )
            )

        if context.image_quality_score is not None:
            metrics["setup_score"] = max(
                0.0,
                min(
                    100.0,
                    context.image_quality_score * 10.0,
                ),
            )

            weighted_scores.append(
                (
                    metrics["setup_score"],
                    AstroQualityEngine.WEIGHTS["setup"],
                    "setup",
                )
            )

        total_weight = sum(
            weight
            for _, weight, _ in weighted_scores
        )

        score = sum(
            value * weight
            for value, weight, _ in weighted_scores
        ) / total_weight

        limiting_factor = min(
            weighted_scores,
            key=lambda item: item[0],
        )[2]

        if (
            context.seeing_arcsec is not None
            and context.image_quality_score is not None
        ):
            confidence = 1.0
        elif (
            context.seeing_arcsec is None
            and context.image_quality_score is None
        ):
            confidence = 0.6
        else:
            confidence = 0.8

        return AstroQualityResult(
            score=round(score, 1),
            confidence=confidence,
            limiting_factor=limiting_factor,
            metrics={
                key: round(value, 1)
                for key, value in metrics.items()
            },
        )