
class NightSliceEvaluator:

    @staticmethod
    def evaluate(slice):

        productivity = 1.0

        productivity -= slice.cloud_cover / 100 * 0.7
        productivity -= slice.moon_penalty * 0.2

        if slice.altitude < 5:
            productivity -= 0.25
        elif slice.altitude < 7:
            productivity -= 0.10

        if slice.humidity > 85:
            productivity -= 0.15

        if slice.wind > 20:
            productivity -= 0.15

        return max(0.0, min(1.0, productivity))
