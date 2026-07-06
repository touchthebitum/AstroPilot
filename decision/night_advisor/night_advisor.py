from decision.night_productivity.night_slice import NightSlice


class NightAdvisor:

    @staticmethod
    def build(timeline):
        actions = []

        for s in timeline:
            time_label = f"{int(s.start_hour):02d}:{int((s.start_hour - int(s.start_hour)) * 60):02d}"

            if s.productivity_score >= 0.90:
                actions.append(
                    f"{time_label} : Conditions excellentes → Continuer les acquisitions"
                )

            elif s.productivity_score >= 0.70:
                actions.append(
                    f"{time_label} : Conditions correctes → Continuer"
                )

            else:
                actions.append(
                    f"{time_label} : Conditions dégradées → Surveiller / attendre"
                )

        return actions

