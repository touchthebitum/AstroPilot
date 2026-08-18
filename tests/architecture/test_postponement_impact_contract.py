from decision.risk.postponement_impact import (
    compute_postponement_impact,
    risk_label_to_score,
)


def test_risk_labels_map_to_canonical_scores():
    assert risk_label_to_score("FAIBLE") == 20
    assert risk_label_to_score("MOYEN") == 50
    assert risk_label_to_score("ÉLEVÉ") == 80
    assert risk_label_to_score("CRITIQUE") == 100


def test_moderate_risk_adds_small_penalty():
    impact = compute_postponement_impact(
        postponement_risk=50,
        confidence="MOYENNE",
        project_priority=30,
        astro_score=100,
    )

    assert impact["postponement_penalty"] == 4.0
    assert impact["urgency_bonus"] == 0
    assert impact["postponement_net_impact"] == -4.0


def test_high_risk_penalizes_bad_night():
    impact = compute_postponement_impact(
        postponement_risk=80,
        confidence="MOYENNE",
        project_priority=30,
        astro_score=50,
    )

    assert impact["postponement_penalty"] == 18.4
    assert impact["urgency_bonus"] == 0
    assert impact["postponement_net_impact"] == -18.4


def test_high_risk_rewards_good_night():
    impact = compute_postponement_impact(
        postponement_risk=80,
        confidence="MOYENNE",
        project_priority=30,
        astro_score=80,
    )

    assert impact["postponement_penalty"] == 0
    assert impact["urgency_bonus"] == 9.2
    assert impact["postponement_net_impact"] == 9.2