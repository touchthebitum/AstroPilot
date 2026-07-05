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

        productive_windows = [
            w for w in night_productivity.windows
            if w.productive
        ]

        if productive_windows:
            tasks.append(
                NightTask(
                    start=f"{productive_windows[0].start_hour:.1f} h",
                    end=f"{productive_windows[-1].end_hour:.1f} h",
                    title="Acquisition",
                    productivity=sum(w.productivity for w in productive_windows) / len(productive_windows),
                )
            )

        tasks.append(
            NightTask(
                "Fin",
                "Fin +10 min",
                "Flats",
            )
        )

        return tasks

