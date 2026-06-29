from night_scheduler_v2 import NightSchedulerV2
from night_strategy import NightStrategy


class NightPlanner:

    def __init__(self):
        self.scheduler = NightSchedulerV2()
        self.strategy = NightStrategy()

    def build_plan(
        self,
        recommended_objects,
        available_hours,
        profile=None,
    ):
        """
        Construit un plan complet de la nuit.
        """
        decision = self.strategy.choose_strategy(
            recommended_objects,
            available_hours,
        )

        recommended_objects = decision["projects"]

        for project in recommended_objects:
            self.schedule_project(project)
        print(self.scheduler.get_events())


        return self.scheduler.get_events()

    def schedule_project(
            self,
            project,
            start_time=22.0,
        ):
            """
            Génère la séquence complète d'un projet.
            """

            self.scheduler.add_event(
                start_time,
                start_time + 0.15,
                "AUTOFOCUS",
                "Autofocus initial"
            )

            self.scheduler.add_event(
                start_time + 0.15,
                start_time + 0.20,
                "FILTER_CHANGE",
                "Installation filtre",
                filter_name=project.get("filter")
            )

            self.scheduler.add_event(
                start_time + 0.20,
                start_time + project["hours"],
                "OBSERVATION",
                f"Observer {project['name']}",
                object_name=project["name"],
                setup=project.get("setup"),
                filter_name=project.get("filter")
            )
    
if __name__ == "__main__":

    planner = NightPlanner()

    projects = [
        {
            "name": "IC1396",
            "hours": 4.0,
            "setup": "Samyang135_2600",
            "filter": "Ha",
            "progress": 35,
            "remaining_hours": 15,
            "roi": 9.3,
        },
        {
            "name": "M31",
            "hours": 4.0,
            "setup": "Samyang135_2600",
            "filter": "LRGB",
            "progress": 92,
            "remaining_hours": 2,
            "roi": 6.8,
        },
    ]

    events = planner.build_plan(
        projects,
        available_hours=4.0,
    )

    for event in events:
        print(event)
