class ScheduleRenderer:

    @staticmethod
    def render(schedule):

        print()
        print("=" * 40)
        print("PLANNING DE LA NUIT")
        print("=" * 40)

        for step in schedule.steps:

            print(f"{step.start} -> {step.end}")
            print(f"  {step.title}")

            if step.description:
                print(f"  {step.description}")

            print()

        print("-" * 40)
        print(f"Heures productives : {schedule.total_productive_hours:.2f} h")
        print(f"Efficacité : {schedule.efficiency:.0%}")
        print("=" * 40)
