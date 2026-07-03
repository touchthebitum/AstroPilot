from decision.models.results.engine_result import EngineResult
from decision.calculators.setup_calculator import SetupCalculator


class ObjectFitEngine:
    """
    Evaluates how well a celestial object fits the imaging setup.
    """

    @staticmethod
    def evaluate(context) -> EngineResult:
        target = context.sky.target
        setup = context.equipment.setup

        capabilities = SetupCalculator.compute(setup)

        object_size_deg = target.angular_size_arcmin / 60

        usable_field_deg = min(
            capabilities.field_width_deg,
            capabilities.field_height_deg,
        )

        occupation = object_size_deg / usable_field_deg

        score = ObjectFitEngine._compute_score(occupation)
        summary = ObjectFitEngine._build_summary(occupation)

        return EngineResult(
            score=score,
            confidence=0.95,
            explanation=summary,
            recommendation=summary,
            limiting_factor=None,
            metrics={
                "target_name": target.name,
                "object_size_deg": object_size_deg,
                "field_width_deg": capabilities.field_width_deg,
                "field_height_deg": capabilities.field_height_deg,
                "occupation": occupation,
                "occupation_percent": occupation * 100,
            },
        )

    @staticmethod
    def _compute_score(occupation: float) -> int:
        if occupation > 1.0:
            return 5
        if 0.45 <= occupation <= 0.70:
            return 100
        if 0.30 <= occupation < 0.45 or 0.70 < occupation <= 0.85:
            return 90
        if 0.20 <= occupation < 0.30 or 0.85 < occupation <= 0.95:
            return 75
        if 0.10 <= occupation < 0.20 or 0.95 < occupation <= 1.0:
            return 55
        return 25

    @staticmethod
    def _build_summary(occupation: float) -> str:
        if occupation > 1.0:
            return "Target is larger than the available field of view."
        if 0.45 <= occupation <= 0.70:
            return "Excellent framing for this setup."
        if 0.30 <= occupation < 0.45 or 0.70 < occupation <= 0.85:
            return "Very good framing for this setup."
        if 0.20 <= occupation < 0.30 or 0.85 < occupation <= 0.95:
            return "Good but not optimal framing."
        if 0.10 <= occupation < 0.20:
            return "Target is small in the field."
        if 0.95 < occupation <= 1.0:
            return "Target is very tight in the field."
        return "Target is too small for this setup."
