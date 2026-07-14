
class NightSliceEvaluator:

    @staticmethod
    def evaluate(slice):

        print(
            f"EVAL altitude={slice.target_altitude:.2f} "
            f"cloud={slice.cloud_cover:.0f} "
            f"moon={getattr(slice, 'moon_penalty', 0.0):.2f}"
        )

        productivity = 1.0

        productivity -= slice.cloud_cover / 100 * 0.7
        productivity -= getattr(slice,"moon_penalty", 0.0) * 0.2

        if slice.target_altitude < 30:
            productivity -= 0.25
        elif slice.target_altitude < 50:
            productivity -= 0.10

        if slice.humidity > 85:
            productivity -= 0.15

        if slice.wind > 20:
            productivity -= 0.15

        productivity = max(0.0, min(1.0, productivity))

        return productivity
