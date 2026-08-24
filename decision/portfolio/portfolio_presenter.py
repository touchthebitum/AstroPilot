from __future__ import annotations
from astropilot.user_profile import get_projects
import math
from datetime import datetime, timedelta


def show_portfolio_completion_forecast(
    roadmap,
    productive_hours_per_night: float = 0.0,
    observing_nights_per_week: float = 0.0,
    night_capacity_source: str = "profile",
    historical_nights: int = 0,
):
    if not roadmap:
        print("\nAucune prévision disponible.")
        return

    print("\n===== COUVERTURE DU PORTEFEUILLE =====")

    projects = get_projects()

    portfolio_remaining = sum(
        max(
            0,
            project.get("target_hours", 0)
            - project.get("hours", 0),
        )
        for project in projects.values()
    )

    planned_hours = sum(
        step.get("hours", 0)
        for step in roadmap
    )

    remaining_after_horizon = max(
        0,
        portfolio_remaining - planned_hours,
    )

    planned_projects = len({
        step["project"]
        for step in roadmap
    })

    planned_nights = len({
        step["night"]
        for step in roadmap
    })

    coverage = (
        planned_hours / portfolio_remaining * 100
        if portfolio_remaining > 0
        else 100.0
    )

    final_date = roadmap[-1].get("date", "?")

    print(f"Projets du portefeuille : {len(projects)}")
    print(f"Projets planifiés : {planned_projects}")
    print(f"Temps restant portefeuille : {portfolio_remaining:.1f} h")
    print(f"Heures planifiées sur l'horizon : {planned_hours:.1f} h")
    print(f"Reste après l'horizon : {remaining_after_horizon:.1f} h")
    print(f"Couverture du portefeuille : {coverage:.1f} %")
    print(f"Nuits planifiées : {planned_nights}")

    if remaining_after_horizon > 0:
        weekly_capacity = (
            productive_hours_per_night
            * observing_nights_per_week
        )

        if weekly_capacity <= 0:
            print("Date de fin estimée : indisponible")
            print(f"Dernière nuit connue : {final_date}")
        else:
            weeks_needed = (
                remaining_after_horizon
                / weekly_capacity
            )

            days_needed = math.ceil(
                weeks_needed * 7
            )

            horizon_end = datetime.strptime(
                final_date,
                "%Y-%m-%d",
            ).date()

            estimated_date = (
                horizon_end
                + timedelta(days=days_needed)
            )

            print(
                "Date de fin estimée : "
                f"vers le {estimated_date}"
            )
            print(
                "Extrapolation au-delà de "
                "l'horizon météo de 7 nuits."
            )

            source_label = (
                "historique"
                if night_capacity_source == "history"
                else "profil"
            )

            print(
                "Base : "
                f"{productive_hours_per_night:.1f} h/nuit "
                f"{source_label} × "
                f"{observing_nights_per_week:.1f} nuits/semaine"
            )

            if night_capacity_source == "history":
                print(
                    "Confiance : MOYENNE — "
                    f"basée sur {historical_nights} nuits observées"
                )
            else:
                print(
                    "Confiance : FAIBLE — "
                    "paramètres du profil"
                )
    else:
        print(f"Date de fin prévue : {final_date}")
        print(
            "Basée sur les prévisions météo disponibles."
        )
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