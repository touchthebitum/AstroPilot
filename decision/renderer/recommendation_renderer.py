

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



