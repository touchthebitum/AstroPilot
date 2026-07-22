from collections.abc import Callable

from decision.models.future_opportunity import FutureOpportunity

def render_opportunity_cost(
    *,
    best_score: dict,
    best_roi: dict,
    session_hours: float,
    remaining_best: float | None,
    remaining_roi: float | None,
    gain_score: float,
    gain_roi: float,
    same_choice: bool,
) -> None:
    print("\n===== COÛT D'OPPORTUNITÉ =====")

    print(f"Si vous photographiez {best_score['name']} :")
    print(f"+{gain_score:.1f}% portefeuille")

    if remaining_best is not None and remaining_best <= session_hours:
        print("Projet terminé")
    else:
        remaining_after = max(0.0, (remaining_best or 0.0) - session_hours)
        print(f"Reste après session : {remaining_after:.1f} h")

    print(f"ROI {gain_score / session_hours:.2f}/h")

    if same_choice:
        return

    print()
    print(f"Si vous photographiez {best_roi['name']} :")
    print(f"+{gain_roi:.1f}% portefeuille")

    if remaining_roi is not None and remaining_roi <= session_hours:
        print("Projet terminé")
    else:
        remaining_after_roi = max(0.0, (remaining_roi or 0.0) - session_hours)
        print(f"Reste après session : {remaining_after_roi:.1f} h")

    print(f"ROI {gain_roi / session_hours:.2f}/h")


def render_strategic_summary(
    *,
    best_score: dict,
    best_roi: dict,
    same_choice: bool,
    chosen_future : FutureOpportunity,
    alt_future: FutureOpportunity,
    chosen_risk: str,
    alt_risk: str,
    progress: float,
    remaining: float | None,
    confidence: str,
    score_gap: float,
) -> None:
    print("\nFacteurs stratégiques :")

    print(
    f"📌 {best_score['name']} : risque {chosen_risk}, "
    f"fenêtres favorables estimées : {chosen_future.good_nights}"
    )

    if not same_choice:
        print(
            f"📌 {best_roi['name']} : risque {alt_risk}, "
            f"fenêtres favorables estimées : {alt_future.good_nights}"
        )

    print("\nUrgence portefeuille :")
    print(f"✓ Progression actuelle : {progress:.1f}%")

    if remaining is not None:
        print(f"✓ Temps restant : {remaining:.1f} h")
    else:
        print("✓ Temps restant : inconnu")

    closure_bonus = best_score.get("closure_bonus", 0)
    if closure_bonus > 0:
        print(f"✓ Bonus clôture disponible : +{closure_bonus:.0f}")

    weather_ratio = chosen_future.weather_ratio
    print(f"Taux météo utilisé : {weather_ratio * 100:.0f}%")

    print("Recommandation finale :")
    print(f"Choisir {best_score['name']}")
    print(f"Confiance : {confidence}")

    if score_gap >= 30:
        print(f"Raison : avantage score de {score_gap:.1f} points")
    elif score_gap >= 10:
        print(f"Raison : avantage score modéré de {score_gap:.1f} points")
    else:
        print("Raison : décision serrée, plusieurs choix valables")


def render_postponement_risk(
    night_projects,
    catalog,
    season_days_remaining,
    estimate_future_opportunities,
):
    print("\n===== RISQUE DE REPORT =====")

    for project in night_projects[:3]:
        catalog_key = project["name"]

        obj = catalog.get(catalog_key, {}).copy()
        obj["catalog_key"] = catalog_key

        days_left = season_days_remaining(obj)

        future = estimate_future_opportunities(catalog_key)

        risk = future.risk

        if risk == "CRITIQUE":
            text = f"fin de fenêtre estimée dans {days_left} jours"
        else:
            text = (
                f"fenêtre restante estimée : "
                f"{future.good_nights} nuits favorables"
                f"(ratio : {future.opportunity_ratio:.1f})"
            )

        print(f"{project['name']} : risque {risk}")
        print(f"   {text}")

def render_after_tonight_roadmap(
    roadmap,
    night_projects,
):
    print("\n===== ROADMAP APRÈS CETTE NUIT =====")

    for i, project in enumerate(roadmap[:3], start=1):
        print(f"\n{i}. {project['name']}")
        print(f"Reste : {project['remaining']:.1f} h")
        print(f"ROI : {project['roi']:.2f}")
        print(f"Gain projet session : +{project['session_gain']:.1f}%")
        print(f"Nuits estimées : {project['estimated_nights']:.1f}")

    print("\n==============================")

    total_remaining = sum(
        p["remaining"]
        for p in roadmap
    )

    total_nights = sum(
        p["estimated_nights"]
        for p in roadmap
    )

    print(f"Temps total restant : {total_remaining:.1f} h")
    print(f"Nuits restantes estimées : {total_nights:.1f}")

def render_top_projects(
    *,
    night_projects: list[dict],
    session_hours: float,
    portfolio_gain_if_shot,
    session_portfolio_gain,
) -> None:
    print("\n===== TOP PROJETS CE SOIR =====")

    for i, project in enumerate(night_projects[:3], start=1):
        gain = portfolio_gain_if_shot(
            project["name"],
            session_hours=session_hours,
        )

        roi = gain / session_hours if session_hours > 0 else 0

        print(
            f"{i}. {project['name']} "
            f"(score {project['final_score']:.1f}) "
            f"gain +{gain:.1f}% "
            f"ROI {roi:.2f}/h"
        )

        session_gain = session_portfolio_gain(
            project["name"],
            session_hours,
        )
        print(f"   Gain session : +{session_gain:.1f}%")

def render_top_roi(
    *,
    night_projects: list[dict],
    session_hours: float,
    portfolio_gain_if_shot,
) -> None:
    print("\n===== TOP ROI SESSION =====")

    roi_projects = []

    for project in night_projects:
        gain = portfolio_gain_if_shot(
            project["name"],
            session_hours=session_hours,
        )

        roi = gain / session_hours if session_hours > 0 else 0

        roi_projects.append(
            {
                "name": project["name"],
                "gain": gain,
                "roi": roi,
            }
        )

    roi_projects.sort(
        key=lambda project: project["roi"],
        reverse=True,
    )

    for i, project in enumerate(roi_projects[:5], start=1):
        print(
            f"{i}. {project['name']} "
            f"ROI {project['roi']:.2f}/h "
            f"(gain +{project['gain']:.1f}%)"
        )

def render_decision_analysis(
    *,
    best_score,
    best_roi,
) -> None:
    print("\n===== ANALYSE DECISION =====")

    if best_score["name"] == best_roi["name"]:
        print(
            f"✓ {best_score['name']} est à la fois "
            f"le meilleur score astro et le meilleur ROI."
        )
