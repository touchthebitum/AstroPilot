from decision.mission.night_mission import NightMission


class MissionPresenter:

    @staticmethod
    def present(mission: NightMission):

        print("\n🌙 ===== MISSION DE CETTE NUIT =====\n")

        print("🎯 Photographier :")
        print(f"{mission.target}")

        print(f"\nConfiance : {mission.confidence:.0%}")

        if mission.risk_report:

            print("\n⚠️ Risque de report")

            print(f"Niveau : {mission.risk_report.level}")

            print(f"Score : {mission.risk_report.score}")

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

            if mission.expected_gain:
                print(f"\n📈 Gain attendu : +{mission.expected_gain:.1f}%")

        if mission.equipment:
            print("\n🎒 Matériel conseillé")
            for item in mission.equipment:
                print(f"• {item}")

        if mission.timeline:
            print("\n🕒 Plan")
            for step in mission.timeline:
                print(f"{step.time}  {step.title}")

        if mission.alternative_target:
            print(f"\nMission suivante : {mission.alternative_target}")