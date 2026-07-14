from .schedule_step import ScheduleStep
from .night_schedule import NightSchedule


class ScheduleBuilder:

    @staticmethod
    def build(productivity):

        steps = []

        steps.append(
            ScheduleStep(
                start="T-30 min",
                end="T-20 min",
                title="Installer le matériel",
                priority=10,
            )
        )

        steps.append(
            ScheduleStep(
                start="T-20 min",
                end="T-10 min",
                title="Mise en station",
                priority=10,
            )
        )

        steps.append(
            ScheduleStep(
                start="T-10 min",
                end="T",
                title="Autofocus",
                priority=9,
            )
        )


        for window in productivity.windows:
            steps.append(
                ScheduleStep(
                    start=f"{window.start_hour:.1f} h",
                    end=f"{window.end_hour:.1f} h",
                    title="Acquisition",
                    description=(
                        f"Productivité estimée "
                        f"({window.productivity:.0%})"
                    ),
                    priority=5,
                    productive=True,
                )
            )

        return NightSchedule(
            steps=steps,
            total_productive_hours=sum(
            w.end_hour - w.start_hour
            for w in productivity.windows
            ),

            efficiency=round(
                sum(w.end_hour - w.start_hour for w in productivity.windows)
                / productivity.astronomical_hours,
                2,) 
                if productivity.astronomical_hours > 0 else 0.0,

            )
