from dataclasses import dataclass
from datetime import timedelta

from astropy.time import Time

from astropilot.catalog import CATALOG
from astropilot.engines.sky_engine import SkyEngine



@dataclass
class SeasonWindow:
    start_date: object
    end_date: object
    peak_date: object
    remaining_days: int | None
    remaining_good_nights: int | None
    urgency: str
    confidence: float


class DynamicSeasonEngine:

    @staticmethod
    def target_altitude_at_time(target, latitude, longitude, obs_time):
        """
        Calcule l'altitude de la cible à une date donnée.
        """

        sky = SkyEngine()

        return sky.target_altitude(
            target["ra"],
            target["dec"],
            Time(obs_time),
            latitude,
            longitude,
        )

    @staticmethod
    def target_visibility_window(
        target,
        latitude,
        longitude,
        start_time,
        end_time,
        min_altitude=30,
    ):
        """
        Détermine la fenêtre de visibilité d'une cible.
        """
        from datetime import timedelta

        current = start_time

        samples = []

        while current <= end_time:

            altitude = DynamicSeasonEngine.target_altitude_at_time(
                target,
                latitude,
                longitude,
                current,
            )

            samples.append((current, altitude))

            current += timedelta(minutes=5)

        return samples


    @staticmethod
    def summary(
        context,
        horizon_days=180,
        min_altitude=30,
        min_useful_hours=2.0,
    ):
        if (
            context.latitude is None
            or context.longitude is None
            or context.observation_time is None
        ):
            return SeasonWindow(
                start_date=None,
                end_date=None,
                peak_date=None,
                remaining_days=None,
                remaining_good_nights=None,
                urgency="UNKNOWN",
                confidence=0.0,
            )

        if isinstance(context.target, str):
            target = CATALOG.get(context.target)
        else:
            target = context.target

        if target is None:
            return SeasonWindow(
                start_date=None,
                end_date=None,
                peak_date=None,
                remaining_days=None,
                remaining_good_nights=None,
                urgency="UNKNOWN",
                confidence=0.0,
            )

        timezone = context.observation_time.tzinfo

        if timezone is None:
            return SeasonWindow(
                start_date=None,
                end_date=None,
                peak_date=None,
                remaining_days=None,
                remaining_good_nights=None,
                urgency="UNKNOWN",
                confidence=0.0,
            )

        observation_date = context.observation_time.date()

        good_dates = []
        peak_date = None
        peak_altitude = float("-inf")

        for day_offset in range(horizon_days + 1):
            current_date = (
                observation_date
                + timedelta(days=day_offset)
            )

            try:
                night_start, night_end = (
                    SkyEngine.astronomical_night_window(
                        date=current_date,
                        latitude=context.latitude,
                        longitude=context.longitude,
                        timezone=timezone,
                    )
                )
            except ValueError:
                continue

            current = night_start
            night_peak_altitude = float("-inf")
            useful_minutes = 0
            sample_minutes = 10

            while current <= night_end:
                altitude = (
                    DynamicSeasonEngine
                    .target_altitude_at_time(
                        target,
                        context.latitude,
                        context.longitude,
                        current,
                    )
                )

                night_peak_altitude = max(
                    night_peak_altitude,
                    altitude,
                )
                if altitude >= min_altitude:
                    useful_minutes += sample_minutes
                current += timedelta(minutes=sample_minutes)

            useful_hours = useful_minutes / 60

            if useful_hours < min_useful_hours:
                continue

            good_dates.append(current_date)

            if night_peak_altitude > peak_altitude:
                peak_altitude = night_peak_altitude
                peak_date = current_date

        if not good_dates:
            return SeasonWindow(
                start_date=None,
                end_date=None,
                peak_date=None,
                remaining_days=0,
                remaining_good_nights=0,
                urgency="UNKNOWN",
                confidence=0.70,
            )

        start_date = good_dates[0]
        end_date = good_dates[-1]

        remaining_days = max(
            0,
            (end_date - observation_date).days,
        )

        if remaining_days <= 14:
            urgency = "HIGH"
        elif remaining_days <= 45:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        horizon_end = (
            observation_date
            + timedelta(days=horizon_days)
        )

        confidence = (
            0.65
            if end_date == horizon_end
            else 0.90
        )

        return SeasonWindow(
            start_date=start_date,
            end_date=end_date,
            peak_date=peak_date,
            remaining_days=remaining_days,
            remaining_good_nights=len(good_dates),
            urgency=urgency,
            confidence=confidence,
        )

