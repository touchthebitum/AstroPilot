from decision.mission.night_mission import NightMission, MissionReason
from decision.risk.risk_engine import RiskEngine
from decision.risk.project_risk_context_builder import ProjectRiskContextBuilder
from decision.night_productivity.night_productivity_engine import NightProductivityEngine
from decision.night_productivity.night_productivity_context import NightProductivityContext
from decision.mission.night_planner import NightPlanner
from decision.intelligence.season_analysis import SeasonAnalysis
from decision.intelligence.analysis_context import AnalysisContext
from decision.season.dynamic_season_engine import DynamicSeasonEngine
from astropilot.catalog import CATALOG
from decision.night_scheduler.night_scheduler import NightScheduler
from decision.mission.mission_input import MissionInput


def _average(values, fallback):
    if not values:
        return fallback
    return sum(values) / len(values)


class MissionAssembler:

    @staticmethod
    def build(
        target,
        summary,
        context,
        equipment,
        timeline,
        alternatives,
        weather=None,
        mission_input: MissionInput | None = None,
    ):

        reasons = []

        for text in summary.positives:
            reasons.append(
                MissionReason(
                    title=text,
                    severity="success",
                )
            )

        for text in summary.negatives:
            reasons.append(
                MissionReason(
                    title=text,
                    severity="warning",
                )
            )

        selected_weather = (
            mission_input.weather
            if mission_input is not None and mission_input.weather is not None
            else weather
        )
        context_weather = getattr(context, "weather", None)
        context_session = getattr(context, "session", None)

        astronomical_hours = (
            mission_input.astronomical_hours
            if mission_input is not None
            else None
        )
        if astronomical_hours is None and mission_input is not None:
            if (
                mission_input.window_start is not None
                and mission_input.window_end is not None
            ):
                astronomical_hours = (
                    mission_input.window_end - mission_input.window_start
                ).total_seconds() / 3600
        if astronomical_hours is None and context_session is not None:
            start = getattr(context_session, "start_time", None)
            end = getattr(context_session, "end_time", None)
            if start is not None and end is not None:
                astronomical_hours = (end - start).total_seconds() / 3600
        if astronomical_hours is None:
            astronomical_hours = 6.0

        cloud_cover = _average(
            getattr(selected_weather, "hourly_clouds", None),
            getattr(context_weather, "cloud_cover", None),
        )
        humidity = _average(
            getattr(selected_weather, "hourly_humidity", None),
            getattr(context_weather, "humidity", None),
        )
        wind = _average(
            getattr(selected_weather, "hourly_wind", None),
            getattr(context_weather, "wind_speed_kmh", None),
        )
        seeing = _average(
            getattr(selected_weather, "hourly_seeing", None),
            getattr(context_weather, "seeing_arcsec", None),
        )
        moon_penalty = (
            mission_input.moon_penalty
            if mission_input is not None
            else None
        )
        if moon_penalty is None:
            moon_penalty = _average(
                getattr(selected_weather, "hourly_moon_penalty", None),
                None,
            )

        productivity = NightProductivityEngine.evaluate(
            NightProductivityContext(
                astronomical_hours=astronomical_hours,
                cloud_cover=20 if cloud_cover is None else cloud_cover,
                moon_penalty=0.2 if moon_penalty is None else moon_penalty,
                altitude_score=8,
                humidity=60 if humidity is None else humidity,
                wind=5 if wind is None else wind,
                seeing=1.5 if seeing is None else seeing,
                weather=selected_weather,
                hourly_clouds=getattr(selected_weather, "hourly_clouds", None),
                hourly_humidity=getattr(selected_weather, "hourly_humidity", None),
                hourly_wind=getattr(selected_weather, "hourly_wind", None),
                hourly_seeing=getattr(selected_weather, "hourly_seeing", None),
                hourly_moon_penalty=getattr(
                    selected_weather,
                    "hourly_moon_penalty",
                    None,
                ),
                display_start_hour=(
                    (
                        mission_input.window_start.hour
                        + mission_input.window_start.minute / 60
                    )
                    if mission_input is not None
                    and mission_input.window_start is not None
                    else (
                        context.session.start_time.hour
                        + context.session.start_time.minute / 60
                    )
                ),
                target=CATALOG[target],
                latitude=context.site.latitude,
                longitude=context.site.longitude,
                observation_time=(
                    mission_input.window_start
                    if mission_input is not None
                    and mission_input.window_start is not None
                    else context.session.start_time
                ),
                ),
            )
        

        schedule = NightScheduler.build(productivity)

        risk_context = ProjectRiskContextBuilder.build(
            target=target,
            context=context,
        )

        risk = RiskEngine.evaluate(risk_context)
        tasks = NightPlanner.build(productivity)


        analysis_context = AnalysisContext(
            target=target,
            weather=selected_weather,
            productivity=productivity,
            risk=risk,
            latitude=context.site.latitude,
            longitude=context.site.longitude,
            observation_time=(
                mission_input.window_start
                if mission_input is not None
                and mission_input.window_start is not None
                else context.session.start_time
            ),
        )


        season_analysis = SeasonAnalysis.analyze(analysis_context)

        samples = DynamicSeasonEngine.target_visibility_window(
            CATALOG[target],
            context.site.latitude,
            context.site.longitude,
            (
                mission_input.window_start
                if mission_input is not None
                and mission_input.window_start is not None
                else context.session.start_time
            ),
            (
                mission_input.window_end
                if mission_input is not None
                and mission_input.window_end is not None
                else context.session.end_time
            ),
        )

        return NightMission(
            target=target,
            confidence=summary.confidence,
            reasons=reasons,
            equipment=equipment,
            window_start=(
                mission_input.window_start if mission_input is not None else None
            ),
            window_end=(
                mission_input.window_end if mission_input is not None else None
            ),
            recommended_hours=(
                mission_input.recommended_hours if mission_input is not None else 0
            ),
            expected_gain=(
                mission_input.expected_gain if mission_input is not None else 0
            ),
            alternative_target=None,
            timeline=timeline,
            risk_report=risk,
            season_analysis=season_analysis,
            productivity=productivity,
            tasks=tasks,
            night_slices=productivity.timeline.slices,
            schedule=schedule,
        )
