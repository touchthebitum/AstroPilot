from decision.mission.night_mission import NightMission
from decision.advisor.night_advisor import NightAdvisor


class MissionPresenter:

    @staticmethod
    def present(mission: NightMission):

        print("\n🌙 ===== MISSION DE CETTE NUIT =====\n")

        print("🎯 Photographier :")
        print(f"{mission.target}")

        print(f"\nConfiance : {mission.confidence:.0%}")

        print()
        print("🌙 Productivité prévue")
        print(f"Heures astronomiques : {mission.productivity.astronomical_hours:.1f} h")
        print(f"Heures productives : {mission.productivity.productive_hours:.1f} h")
        print(f"Confiance productivité : {mission.productivity.confidence:.0%}")
        print()

        if mission.productivity.windows:
            print()
            print("🌙 Fenêtres optimales")

            for w in mission.productivity.windows:
                base = mission.productivity.display_start_hour

                start = base + w.start_hour
                end = base + w.end_hour

                start_h = int(start) % 24
                start_m = int((start - int(start)) * 60)

                end_h = int(end) % 24
                end_m = int((end - int(end)) * 60)
                
                print(
                    f"{start_h:02d}:{start_m:02d} → {end_h:02d}:{end_m:02d}   "
                    f"productivité {w.productivity:.0%}   "
                    f"{w.reason}"
                )

        if mission.risk_report:

            print("\n⚠️ Risque de report")

            print(f"Niveau : {mission.risk_report.level}")

            print(f"Score : {mission.risk_report.score}")

            print(f"Nuits nécessaires estimées : {mission.risk_report.context.required_nights}")

            for line in mission.risk_report.explanation:
                print(f"• {line}")

        if mission.window_start and mission.window_end:
            print(f"\n🕒 Fenêtre optimale : {mission.window_start} → {mission.window_end}")

        if mission.recommended_hours >0:
            print(f"⏱ Temps conseillé : {mission.recommended_hours:.1f} h")

        if mission.expected_gain >0:
            print(f"📈 Gain attendu : +{mission.expected_gain:.1f}%")

        if mission.alternative_target:
            print(f"🔁 Alternative : {mission.alternative_target}")


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


        advices = NightAdvisor.build(mission)

        print("\n🌙 Conseils de la nuit")

        for advice in advices:
            print(f"[{advice.time}] {advice.message}")

        if mission.timeline:
            print("\n🕒 Plan")
            for step in mission.timeline:
                print(f"{step.time}  {step.title}")

        if mission.alternative_target:
            print(f"\nMission suivante : {mission.alternative_target}")
