from datetime import datetime, timedelta

from decision.mission.night_mission import NightMission
from decision.advisor.night_advisor import NightAdvisor
from decision.time_math import add_elapsed_time


def _local_time_text(value: datetime) -> str:
    text = value.strftime("%H:%M")
    if (
        value.tzinfo is None
        or value.utcoffset() is None
        or value.replace(fold=0).utcoffset()
        == value.replace(fold=1).utcoffset()
    ):
        return text

    offset = value.utcoffset()
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    suffix = f"UTC{sign}{hours:02d}"
    if minutes:
        suffix += f":{minutes:02d}"
    return f"{text} ({suffix})"


def _window_time_text(
    productivity,
    offset_hours: float,
    timeline_start: datetime | None,
) -> str:
    if (
        timeline_start is None
        or timeline_start.tzinfo is None
        or timeline_start.utcoffset() is None
    ):
        hour = productivity.display_start_hour + offset_hours
        hour_text = int(hour) % 24
        minute_text = int((hour - int(hour)) * 60)
        return f"{hour_text:02d}:{minute_text:02d}"

    instant = add_elapsed_time(
        timeline_start,
        timedelta(hours=offset_hours),
    )
    return _local_time_text(instant.astimezone(timeline_start.tzinfo))


class MissionPresenter:

    @staticmethod
    def present(
        mission: NightMission,
        *,
        timeline_start: datetime | None = None,
    ):

        print("\n🌙 ===== MISSION DE CETTE NUIT =====\n")

        print("🎯 Photographier :")
        print(f"{mission.target}")

        print(f"\nConfiance : {mission.confidence:.0%}")

        print()
        print("🌙 Productivité prévue")
        print(f"Heures astronomiques : {mission.productivity.astronomical_hours:.1f} h")
        print(f"Heures productives : {mission.productivity.productive_hours:.1f} h")
        print(f"Part productive : {mission.productivity.confidence:.0%}")
        print()

        if mission.astro_quality is not None:
            score = mission.astro_quality.score

            if score >= 90:
                label = "Excellente"
            elif score >= 75:
                label = "Très bonne"
            elif score >= 60:
                label = "Bonne"
            elif score >= 40:
                label = "Moyenne"
            else:
                label = "Faible"

            limiting_labels = {
                "altitude": "Altitude",
                "clouds": "Nuages",
                "moon": "Lune",
                "seeing": "Seeing",
                "setup": "Setup",
            }

            limiting_factor = limiting_labels.get(
                mission.astro_quality.limiting_factor,
                mission.astro_quality.limiting_factor,
            )

            print("🌌 Qualité astrophotographique")
            print(f"AQI : {score:.0f}/100 — {label}")

            if limiting_factor:
                print(f"Facteur limitant : {limiting_factor}")

            print(
                "Complétude AQI : "
                f"{mission.astro_quality.confidence:.0%}"
            )
            print()

        if mission.dew_risk is not None:
            risk_labels = {
                "LOW": "Faible",
                "MEDIUM": "Modéré",
                "HIGH": "Élevé",
                "CRITICAL": "Critique",
            }

            risk_label = risk_labels.get(
                mission.dew_risk.risk,
                mission.dew_risk.risk,
            )

            print("💧 Risque de rosée")
            print(f"Niveau : {risk_label}")
            print(
                f"Point de rosée : "
                f"{mission.dew_risk.dew_point_c:.1f} °C"
            )
            print(
                f"Marge thermique : "
                f"{mission.dew_risk.spread_c:.1f} °C"
            )
            print()

        if mission.productivity.windows:
            print()
            print("🌙 Fenêtres optimales")

            for w in mission.productivity.windows:
                start_text = _window_time_text(
                    mission.productivity,
                    w.start_hour,
                    timeline_start,
                )
                end_text = _window_time_text(
                    mission.productivity,
                    w.end_hour,
                    timeline_start,
                )

                print(
                    f"{start_text} → {end_text}   "
                    f"productivité {w.productivity:.0%}   "
                    f"{w.reason}"
                )

        if mission.risk_report:

            print("\n⚠️ Risque de report")

            print(f"Niveau : {mission.risk_report.level}")

            print(f"Score : {mission.risk_report.score}")

            capacity_source = {
                "profile": "profil",
                "history": "historique",
            }.get(
                mission.risk_report.context.night_capacity_source,
                mission.risk_report.context.night_capacity_source,
            )

            print(
                "Capacité moyenne estimée : "
                f"{mission.risk_report.context.productive_hours_per_night:.1f} "
                f"h/nuit ({capacity_source})"
            )

            print(
                "Nuits nécessaires estimées : "
                f"{mission.risk_report.context.required_nights}"
            )

            for line in mission.risk_report.explanation:
                print(f"• {line}")

        if mission.window_start and mission.window_end:
            print(f"\n🕒 Fenêtre optimale : {mission.window_start} → {mission.window_end}")

        if mission.recommended_hours >0:
            print(f"⏱ Temps conseillé : {mission.recommended_hours:.1f} h")

        if mission.expected_gain >0:
            print(f"📈 Gain attendu : +{mission.expected_gain:.1f}%")


        print("\nPourquoi cette mission ?")

        for reason in mission.reasons:

            if reason.severity == "success":
                icon = "✓"

            elif reason.severity == "warning":
                icon = "⚠"

            else:
                icon = "•"

            if reason.value:
                print(f"{icon} {reason.title} ({reason.value})")
            else:
                print(f"{icon} {reason.title}")

        if mission.season_analysis:

            print("\n🌙 Analyse saison")

            print(f"Conclusion : {mission.season_analysis.conclusion}")

            print(
                f"Confiance : "
                f"{mission.season_analysis.confidence * 100:.0f}%"
            )

            season = mission.season_analysis.data

            print(f"Jours restants : {season['remaining_days']}")
            print(
                f"Nuits favorables : "
                f"{season['remaining_good_nights']}"
            )
            print(f"Urgence : {season['urgency']}")

        print("\n🗓️ Plan de nuit")

        for task in mission.tasks:
            print(f"{task.start} → {task.end}  {task.title}")


        if mission.equipment:
            print("\n🎒 Matériel conseillé")
            for item in mission.equipment:
                print(f"• {item}")

        if mission.selected_filter is not None:
            print(
                f"• 🔴 Filtre : "
                f"{mission.selected_filter.name}"
            )


        advices = NightAdvisor.build(mission)

        print("\n🌙 Conseils de la nuit")

        for advice in advices:
            print(f"[{advice.time}] {advice.message}")
