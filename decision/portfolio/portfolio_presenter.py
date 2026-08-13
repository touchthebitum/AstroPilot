from __future__ import annotations

def show_portfolio_completion_forecast(roadmap):

    if not roadmap:
        print("\nAucune prévision disponible.")
        return

    print("\n===== FIN DU PORTEFEUILLE =====")
    
    last_step = roadmap[-1]

    final_date = last_step.get("date", "?")

    total_hours = sum(
        step.get("hours", 0)
        for step in roadmap
    )

    active_projects = len({
        step["project"]
        for step in roadmap
    })

    planned_capacity = sum(
        step.get("hours", 0)
        for step in roadmap
    )

    coverage = (
        planned_capacity / total_hours * 100
        if total_hours > 0 else 0
    )

    print(f"Projets actifs : {active_projects}")
    print(f"Temps total restant : {total_hours:.1f} h")
    print(f"Capacité future connue : {planned_capacity:.1f} h")
    print(f"Couverture : {coverage:.1f} %")
    print(f"Nuits restantes : {len(roadmap)}")
    print(f"Fin estimée du portefeuille : {final_date}")

    print("\n===== ÉTAT PRÉVU EN FIN DE ROADMAP =====")

    displayed = set()

    for step in roadmap:
        project = step["project"]

        if project in displayed:
            continue

        displayed.add(project)

        project_steps = [
            s for s in roadmap
            if s["project"] == project
        ]

        start_date = project_steps[0].get("date", "?")
        end_date = project_steps[-1].get("date", "?")

        target_hours = project_steps[0]["target_hours"]

        nights = len(project_steps)

        remaining_after = project_steps[-1].get("remaining_after", 0)

        completed = max(0.0, target_hours - remaining_after)

        progress = (
            completed / target_hours
            if target_hours > 0 else 1.0
        )

        percent = progress * 100

        if remaining_after <= 0:
            icon = "✓"
            status = "Terminé"
        else:
            icon = "◐"
            status = (
                f"{completed:.1f}/{target_hours:.1f} h "
                f"({percent:.0f} %) • reste {remaining_after:.1f} h"
        )

        print(f"{icon} {project:<12} {status}")