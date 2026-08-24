from dataclasses import dataclass

@dataclass(frozen=True)
class NightTask:
    start: str
    end: str

    title: str
    description: str = ""

    priority: int = 0

    productivity: float = 0.0


class NightPlanner:

    @staticmethod
    def build(night_productivity):
        tasks = [
            NightTask("T-30 min", "T-20 min", "Installer le matériel"),
            NightTask("T-20 min", "T-10 min", "Mise en station"),
            NightTask("T-10 min", "T", "Autofocus"),
        ]

        tasks.append(
            NightTask(
                "Fin",
                "Fin +10 min",
                "Flats",
            )
        )

        return tasks

