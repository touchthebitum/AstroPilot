from decision.productivity.productivity_result import ProductivityResult
import math


class ProductivityEngine:

    @staticmethod
    def evaluate(remaining_hours : float):

        average_productive_hours = 4.0

        required_nights = math.ceil(
            remaining_hours / average_productive_hours
        )


        return ProductivityResult(
            productive_hours=4.0,
            efficiency=1.0,
            lost_cloud_hours=0.0,
            lost_moon_hours=0.0,
            lost_altitude_hours=0.0,
            required_nights=required_nights,
        )