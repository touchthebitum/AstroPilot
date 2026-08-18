from __future__ import annotations


def risk_label_to_score(risk):
    mapping = {
        "FAIBLE": 20,
        "MOYEN": 50,
        "ÉLEVÉ": 80,
        "CRITIQUE": 100,
    }

    return mapping.get(
        str(risk).upper(),
        50,
    )


def compute_postponement_impact(
    postponement_risk,
    confidence="MOYENNE",
    project_priority=50,
    astro_score=0,
):
    if postponement_risk is None:
        postponement_risk = 0

    risk = max(
        0,
        min(float(postponement_risk), 100),
    )

    priority = max(
        0,
        min(float(project_priority), 100),
    )

    confidence_factor = {
        "HAUTE": 0.8,
        "MOYENNE": 1.0,
        "BASSE": 1.2,
    }.get(
        str(confidence).upper(),
        1.0,
    )

    priority_factor = 1.0 + priority / 200

    penalty = 0
    urgency_bonus = 0
    reason = "Risque de report faible ou neutre."

    if risk >= 70 and astro_score >= 70:
        urgency_bonus = (
            risk
            * 0.10
            * priority_factor
        )

        reason = (
            "Bonne nuit et risque de report élevé : "
            "bonus d'urgence."
        )

    elif risk >= 70:
        penalty = (
            risk
            * 0.20
            * confidence_factor
            * priority_factor
        )

        reason = (
            "Risque de report élevé mais conditions "
            "insuffisantes : pénalité prudente."
        )

    elif risk >= 40:
        penalty = (
            risk
            * 0.08
            * confidence_factor
        )

        reason = (
            "Risque de report modéré : "
            "légère pénalité."
        )

    else:
        penalty = risk * 0.03

        reason = (
            "Risque de report faible : "
            "impact minimal."
        )

    net_impact = urgency_bonus - penalty

    return {
        "postponement_penalty": round(
            penalty,
            2,
        ),
        "urgency_bonus": round(
            urgency_bonus,
            2,
        ),
        "postponement_net_impact": round(
            net_impact,
            2,
        ),
        "postponement_reason": reason,
    }