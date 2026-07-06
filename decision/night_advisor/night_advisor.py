from decision.night_productivity.night_slice import NightSlice


class NightAdvisor:

    @staticmethod
    def build(timeline):

        actions = []

        previous = None

        for s in timeline:

            time_label = (
                f"{int(s.start_hour):02d}:"
                f"{int((s.start_hour - int(s.start_hour)) * 60):02d}"
            )

            # Début d'une excellente fenêtre
            if (
                s.productivity_score >= 0.90
                and (
                    previous is None
                    or previous.productivity_score < 0.90
                )
            ):
                actions.append(
                    f"{time_label} : Début d'une excellente fenêtre d'acquisition."
                )

            # Fin d'une excellente fenêtre
            elif (
                previous is not None
                and previous.productivity_score >= 0.90
                and s.productivity_score < 0.90
            ):
                actions.append(
                    f"{time_label} : Fin de la meilleure fenêtre d'acquisition."
                )

            previous = s


        return actions

