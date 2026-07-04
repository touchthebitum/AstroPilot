from datetime import datetime, timedelta

from decision.mission.night_mission import MissionEvent


class TimelineBuilder:

    @staticmethod
    def build(best_window):

        print("DEBUG TimelineBuilder V2")

        if not best_window:
            return []

        start = datetime.strptime(best_window["start"], "%H:%M")
        end = datetime.strptime(best_window["end"], "%H:%M")

        return [
            MissionEvent((start - timedelta(minutes=20)).strftime("%H:%M"), "Installation"),
            MissionEvent((start - timedelta(minutes=10)).strftime("%H:%M"), "Mise en station"),
            MissionEvent((start - timedelta(minutes=2)).strftime("%H:%M"), "Autofocus"),
            MissionEvent(start.strftime("%H:%M"), "Début des acquisitions"),
            MissionEvent(end.strftime("%H:%M"), "Fin recommandée"),
        ]