import math

from decision.quality.astro_quality_result import AstroQualityResult


class AstroQualityEngine:
    WEIGHTS = {
        "altitude": 0.18,
        "clouds": 0.27,
        "moon": 0.13,
        "seeing": 0.18,
        "setup": 0.14,
        "dew": 0.10,
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
        specifications = (
            ("altitude", "altitude_score", "target_altitude_deg", -90, 90, AstroQualityEngine._altitude_score),
            ("clouds", "cloud_score", "cloud_cover_percent", 0, 100, AstroQualityEngine._cloud_score),
            ("moon", "moon_score", "moon_penalty", 0, 1, AstroQualityEngine._moon_score),
            ("seeing", "seeing_score", "seeing_arcsec", 0, None, AstroQualityEngine._seeing_score),
            ("setup", "setup_score", "image_quality_score", None, None, lambda value: max(0.0, min(100.0, value * 10))),
            ("dew", "dew_score", "dew_score", 0, 100, lambda value: value),
        )
        metrics = {}
        weighted_scores = []
        missing = []
        for name, key, attribute, lower, upper, transform in specifications:
            value = getattr(context, attribute, None)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or (lower is not None and value < lower)
                    or (upper is not None and value > upper)):
                missing.append(name)
                continue
            score = transform(value)
            metrics[key] = round(score, 1)
            weighted_scores.append((score, AstroQualityEngine.WEIGHTS[name], name))

        completeness = sum(weight for _, weight, _ in weighted_scores)
        # The historical normalized score is diagnostic only when evidence is partial.
        score = (sum(value * weight for value, weight, _ in weighted_scores)
                 / completeness) if completeness else 0.0
        eligible = not missing
        return AstroQualityResult(
            score=round(score, 1),
            confidence=round(completeness, 2),
            limiting_factor=min(weighted_scores, key=lambda item: item[0])[2] if weighted_scores else None,
            metrics=metrics,
            completeness=round(completeness, 2),
            missing_metrics=tuple(missing),
            decision_eligible=eligible,
            decision_score=round(score, 1) if eligible else None,
            status="complete" if eligible else "insufficient_evidence",
        )
