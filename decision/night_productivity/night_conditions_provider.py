class NightConditionsProvider:

    @staticmethod
    def _hour_index(hour):
        return int(hour)

    @staticmethod
    def _value(hour, values, fallback):
        if not values:
            return fallback

        index = NightConditionsProvider._hour_index(hour)

        if index < 0:
            return fallback

        if index >= len(values):
            return values[-1]

        return values[index]

    @staticmethod
    def cloud(current, context):

        if (
            context.weather
            and context.weather.hourly_clouds
            and 
    len(context.weather.hourly_clouds) > 0
        ):
            index = min(int(current * 4), 
    len(context.weather.hourly_clouds) - 1)

            return context.weather.hourly_clouds[index]
        return context.cloud_cover

    @staticmethod
    def humidity(hour, context):
        if context.weather and context.weather.hourly_humidity:
            return NightConditionsProvider._value(
                hour,
                context.weather.hourly_humidity,
                context.humidity,
            )

        return context.humidity

    @staticmethod
    def wind(hour, context):
        if context.weather and context.weather.hourly_wind:
            return NightConditionsProvider._value(
                hour,
                context.weather.hourly_wind,
                context.wind,
            )

        return context.wind

    @staticmethod
    def seeing(hour, context):
        return NightConditionsProvider._value(
            hour,
            context.hourly_seeing,
            context.seeing,
        )

    @staticmethod
    def moon_penalty(hour, context):
        return NightConditionsProvider._value(
            hour,
            context.hourly_moon_penalty,
            context.moon_penalty,
        )

    @staticmethod
    def altitude(hour, context):
        return context.altitude_score
