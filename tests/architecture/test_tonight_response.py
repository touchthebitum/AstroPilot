from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timezone

import pytest

from decision.filtering.selected_filter import SelectedFilter
from decision.intelligence.analysis_result import AnalysisResult
from decision.mission.night_mission import MissionReason, NightMission
from decision.mission.night_planner import NightTask
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.candidate_rejection import (
    CandidateRejection,
    CandidateRejectionBasis,
)
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_window import NightWindow
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.quality.astro_quality_result import AstroQualityResult
from decision.recommendation.recommendation import Recommendation
from decision.quality.dew_risk_result import DewRiskResult
from decision.risk.project_risk_context import ProjectRiskContext
from decision.risk.risk_report import RiskReport
from decision.services.tonight_application_service import (
    TonightResult,
    TonightStatus,
)
from decision.services.tonight_response import (
    TargetDecisionStatus,
    TonightResponse,
)
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


def make_candidate(
    provenance=CandidateProvenance.PROJECT,
    *,
    name="Andromeda",
    catalog_key="M31",
    decision_score=77.0,
    final_score=79.0,
):
    return Candidate(
        name=name,
        catalog_key=catalog_key,
        priority=1.0,
        astro_score=82.0,
        final_score=final_score,
        decision_score=decision_score,
        portfolio_score=75.0,
        global_score=81.0,
        setup_score=68.0,
        best_setup="widefield",
        closure_bonus=0.0,
        provenance=provenance,
    )


def test_target_decision_status_has_exact_transport_values():
    assert {status.value for status in TargetDecisionStatus} == {
        "recommended",
        "viable",
        "not_recommended",
        "insufficient_evidence",
    }


@pytest.mark.parametrize(
    "status",
    [
        TonightStatus.FORECAST_UNAVAILABLE,
        TonightStatus.NO_NIGHT,
        TonightStatus.NO_CANDIDATE,
        TonightStatus.NO_RECOMMENDATION,
    ],
)
def test_partial_results_produce_stable_transport_status(status):
    response = TonightResponse.from_result(
        TonightResult(None, None, None, status=status)
    )

    assert response.to_dict() == {
        "status": status.value,
        "decision_id": None,
        "night_date": None,
        "target": None,
        "catalog_key": None,
        "target_common_name": None,
        "action": None,
        "provenance": None,
        "target_decision_status": None,
        "shortlist_entries": [],
        "alternatives": [],
        "rejected_targets": [],
        "insufficient_evidence_targets": [],
        "recommendation_confidence": None,
        "mission_confidence": None,
        "scores": {},
        "window_start": None,
        "window_end": None,
        "recommended_hours": 0.0,
        "expected_gain": 0.0,
        "equipment": [],
        "selected_filter": None,
        "astro_quality": None,
        "productivity": None,
        "dew_risk": None,
        "postponement_risk": None,
        "season": None,
        "explanation": None,
        "reasons": [],
        "tasks": [],
        "advices": [],
        "weather_decision": None,
    }


def test_complete_result_maps_only_json_compatible_values():
    candidate = make_candidate()
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=0.91,
    )
    mission = NightMission(
        target="Andromeda",
        confidence=0.87,
        reasons=[
            MissionReason("Excellent altitude", "success", "72°"),
            MissionReason("Thin cloud risk", "warning"),
            MissionReason("Broadband session", "info"),
        ],
        equipment=["Widefield", "ASI2600MC"],
        window_start=datetime(2026, 9, 1, 22, 30, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 2, 0, tzinfo=timezone.utc),
        recommended_hours=3.5,
        expected_gain=12.0,
        selected_filter=SelectedFilter("L-Pro", "broadband", 50.0),
        astro_quality=AstroQualityResult(
            score=78.0,
            confidence=0.84,
            limiting_factor="clouds",
            metrics={"altitude": 91.0, "clouds": 64.0},
        ),
        productivity=NightProductivityResult(
            astronomical_hours=6.0,
            productive_hours=3.5,
            confidence=0.82,
            cloud_loss=1.0,
            moon_loss=0.5,
            altitude_loss=0.25,
            weather_loss=0.75,
            display_start_hour=22,
            windows=[
                NightWindow(
                    start_hour=1.5,
                    end_hour=4.25,
                    productivity=0.88,
                    altitude=67.0,
                    cloud_cover=12.0,
                    moon_penalty=0.1,
                    seeing=1.4,
                    productive=True,
                    reason="stable_conditions",
                )
            ],
        ),
        dew_risk=DewRiskResult(
            dew_point_c=7.2,
            spread_c=1.8,
            risk="HIGH",
            score=82.0,
        ),
        risk_report=RiskReport(
            level="MEDIUM",
            score=63,
            explanation=["Only two favorable nights remain"],
            context=ProjectRiskContext(
                priority=8.0,
                remaining_hours=5.5,
                completion=0.45,
                season_remaining_days=21,
                favorable_nights=2,
                required_nights=2,
                productive_hours_per_night=3.5,
                night_capacity_source="history",
                historical_nights=6,
            ),
        ),
        season_analysis=AnalysisResult(
            analysis_name="season",
            conclusion="Prime autumn window",
            confidence=0.89,
            data={
                "peak_date": date(2026, 10, 12),
                "months": ("September", "October"),
            },
        ),
        tasks=[
            NightTask(
                "T-30 min",
                "T-20 min",
                "Installer le matériel",
                priority=2,
            )
        ],
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=mission,
        )
    ).to_dict()

    assert response["status"] == "available"
    assert response["night_date"] == "2026-09-01"
    assert response["target"] == "Andromeda"
    assert response["catalog_key"] == "M31"
    assert response["target_common_name"] == "Galaxie d’Andromède"
    assert response["action"] == "start_project"
    assert response["provenance"] == "project"
    assert response["target_decision_status"] == "recommended"
    assert response["recommendation_confidence"] == 0.91
    assert response["scores"] == {
        "astro_score": 82.0,
        "decision_score": 77.0,
        "final_score": 79.0,
        "portfolio_score": 75.0,
        "global_score": 81.0,
        "setup_score": 68.0,
    }
    assert response["window_start"] == "2026-09-01T22:30:00+00:00"
    assert response["selected_filter"] == {
        "name": "L-Pro",
        "filter_type": "broadband",
        "bandwidth_nm": 50.0,
    }
    assert response["astro_quality"] == {
        "score": 78.0,
        "confidence": 0.84,
        "label": "very_good",
        "limiting_factor": "clouds",
        "metrics": {"altitude": 91.0, "clouds": 64.0},
    }
    assert response["productivity"] == {
        "astronomical_hours": 6.0,
        "productive_hours": 3.5,
        "productive_fraction": 0.82,
        "confidence": 0.82,
        "cloud_loss": 1.0,
        "moon_loss": 0.5,
        "altitude_loss": 0.25,
        "weather_loss": 0.75,
        "display_start_hour": 22,
        "windows": [
            {
                "start_offset_hours": 1.5,
                "end_offset_hours": 4.25,
                "start_time": "23:30",
                "end_time": "02:15",
                "productivity": 0.88,
                "productive": True,
                "reason": "stable_conditions",
                "altitude": 67.0,
                "cloud_cover": 12.0,
                "moon_penalty": 0.1,
                "seeing": 1.4,
            }
        ],
    }
    assert response["dew_risk"] == {
        "level": "HIGH",
        "score": 82.0,
        "dew_point_c": 7.2,
        "spread_c": 1.8,
    }
    assert response["postponement_risk"] == {
        "level": "MEDIUM",
        "score": 63,
        "explanations": ["Only two favorable nights remain"],
        "required_nights": 2,
        "productive_hours_per_night": 3.5,
        "capacity_source": "history",
        "historical_nights": 6,
        "remaining_hours": 5.5,
        "favorable_nights": 2,
        "season_remaining_days": 21,
    }
    assert response["season"] == {
        "analysis_name": "season",
        "conclusion": "Prime autumn window",
        "confidence": 0.89,
        "data": {
            "peak_date": "2026-10-12",
            "months": ["September", "October"],
        },
    }
    assert response["explanation"] == {
        "positives": [
            {
                "title": "Excellent altitude",
                "severity": "success",
                "value": "72°",
            }
        ],
        "warnings": [
            {
                "title": "Thin cloud risk",
                "severity": "warning",
                "value": None,
            }
        ],
        "information": [
            {
                "title": "Broadband session",
                "severity": "info",
                "value": None,
            }
        ],
        "limiting_factors": ["clouds"],
    }
    assert response["reasons"] == [
        {
            "title": "Excellent altitude",
            "severity": "success",
            "value": "72°",
        },
        {
            "title": "Thin cloud risk",
            "severity": "warning",
            "value": None,
        },
        {
            "title": "Broadband session",
            "severity": "info",
            "value": None,
        },
    ]
    assert response["tasks"] == [
        {
            "start": "T-30 min",
            "end": "T-20 min",
            "title": "Installer le matériel",
            "description": "",
            "priority": 2,
        }
    ]
    assert response["advices"] == [
        {
            "time": "Début",
            "priority": "INFO",
            "category": "general",
            "message": "Aucun conseil particulier pour cette nuit.",
        }
    ]


def test_discovery_provenance_is_mapped_from_recommendation_candidate():
    candidate = make_candidate(CandidateProvenance.DISCOVERY)
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=None,
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=None,
        )
    )

    assert response.provenance == "discovery"
    assert (
        response.target_decision_status
        is TargetDecisionStatus.RECOMMENDED
    )


def test_shortlist_entries_expose_only_compact_candidate_fields():
    primary = make_candidate()
    first = make_candidate(
        CandidateProvenance.DISCOVERY,
        name="Orion",
        catalog_key="M42",
        decision_score=74.0,
        final_score=76.0,
    )
    second = make_candidate(
        name="Triangulum",
        catalog_key="M33",
        decision_score=71.0,
        final_score=73.0,
    )
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=primary,
            shortlist_entries=(first, second),
        ),
        confidence=None,
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=None,
        )
    ).to_dict()

    assert response["shortlist_entries"] == [
        {
            "target": "Orion",
            "catalog_key": "M42",
            "provenance": "discovery",
            "decision_score": 74.0,
            "final_score": 76.0,
            "target_decision_status": None,
        },
        {
            "target": "Triangulum",
            "catalog_key": "M33",
            "provenance": "project",
            "decision_score": 71.0,
            "final_score": 73.0,
            "target_decision_status": None,
        },
    ]


def test_shortlist_publishes_only_prequalified_viable_entries():
    primary = make_candidate()
    first = make_candidate(name="Orion", catalog_key="M42")
    second = make_candidate(name="Triangulum", catalog_key="M33")
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=primary,
            shortlist_entries=(first, second),
        ),
        confidence=None,
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=None,
        ),
        viable_shortlist_catalog_keys={"M42"},
    ).to_dict()

    assert [entry["catalog_key"] for entry in response["shortlist_entries"]] == [
        "M42",
        "M33",
    ]
    assert [
        entry["target_decision_status"]
        for entry in response["shortlist_entries"]
    ] == ["viable", None]


def test_alternatives_serialize_only_preselected_candidates():
    primary = make_candidate()
    first = make_candidate(name="Orion", catalog_key="M42")
    second = make_candidate(name="Triangulum", catalog_key="M33")
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=primary,
            shortlist_entries=(first, second),
        ),
        confidence=None,
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=None,
        ),
        viable_shortlist_catalog_keys={"M42"},
        selected_alternatives=(first,),
    ).to_dict()

    assert response["alternatives"] == [
        {
            "target": "Orion",
            "catalog_key": "M42",
            "provenance": "project",
            "decision_score": first.decision_score,
            "final_score": first.final_score,
            "target_decision_status": "viable",
        }
    ]


def test_alternatives_default_to_empty():
    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=None,
            mission=None,
        )
    ).to_dict()

    assert response["alternatives"] == []


def test_unknown_recommendation_and_mission_confidence_remain_none():
    candidate = make_candidate()
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=None,
    )
    mission = NightMission(
        target="Andromeda",
        confidence=None,
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=recommendation,
            mission=mission,
        )
    )

    assert response.recommendation_confidence is None
    assert response.mission_confidence is None


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (90.0, "excellent"),
        (75.0, "very_good"),
        (60.0, "good"),
        (40.0, "average"),
        (39.9, "low"),
    ],
)
def test_astro_quality_labels_are_stable(score, label):
    mission = NightMission(
        target="Andromeda",
        confidence=0.8,
        astro_quality=AstroQualityResult(score=score, confidence=0.9),
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=None,
            mission=mission,
        )
    )

    assert response.astro_quality.label == label


def test_caution_preserves_active_transport_and_internal_result_identities():
    candidate = make_candidate()
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=0.91,
    )
    mission = NightMission(target="Andromeda", confidence=0.87)
    result = TonightResult(
        night={"date": date(2026, 9, 1)},
        recommendation=recommendation,
        mission=mission,
    )
    decision = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
        admissibility=WeatherDecisionAdmissibility.CAUTION,
        reasons=("provider_reliability_unavailable",),
    )

    response = TonightResponse.from_result(
        result,
        weather_decision=decision,
    ).to_dict()

    assert response["status"] == "available"
    assert response["target"] == "Andromeda"
    assert response["action"] == "start_project"
    assert response["target_decision_status"] == "recommended"
    assert response["weather_decision"] == {
        "evidence_quality": "insufficient",
        "admissibility": "caution",
        "reasons": ["provider_reliability_unavailable"],
        "presentation": {
            "label": "Validation météo partielle",
            "summary": (
                "Certaines preuves historiques de fiabilité ne sont pas encore "
                "disponibles ; cela ne signifie pas que la météo est mauvaise."
            ),
        },
    }
    assert result.recommendation is recommendation
    assert result.mission is mission


def test_refused_weather_decision_redacts_active_transport_only():
    candidate = make_candidate()
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
        ),
        confidence=0.91,
    )
    mission = NightMission(
        target="Andromeda",
        confidence=0.87,
        equipment=["Widefield"],
        window_start=datetime(2026, 9, 1, 22, tzinfo=timezone.utc),
        window_end=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
        recommended_hours=3.0,
        expected_gain=8.0,
        selected_filter=SelectedFilter("L-Pro", "broadband", 50.0),
        tasks=[NightTask("T-30 min", "T-20 min", "Installer")],
    )
    result = TonightResult(
        night={"date": date(2026, 9, 1)},
        recommendation=recommendation,
        mission=mission,
    )
    decision = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
        admissibility=WeatherDecisionAdmissibility.REFUSED,
        reasons=("selected_window_uncovered",),
    )

    response = TonightResponse.from_result(
        result,
        weather_decision=decision,
    ).to_dict()

    assert response == {
        "status": "weather_refused",
        "decision_id": None,
        "night_date": "2026-09-01",
        "target": None,
        "catalog_key": None,
        "target_common_name": None,
        "action": None,
        "provenance": None,
        "target_decision_status": "insufficient_evidence",
        "shortlist_entries": [],
        "alternatives": [],
        "rejected_targets": [],
        "insufficient_evidence_targets": [],
        "recommendation_confidence": None,
        "mission_confidence": None,
        "scores": {},
        "window_start": None,
        "window_end": None,
        "recommended_hours": 0.0,
        "expected_gain": 0.0,
        "equipment": [],
        "selected_filter": None,
        "astro_quality": None,
        "productivity": None,
        "dew_risk": None,
        "postponement_risk": None,
        "season": None,
        "explanation": None,
        "reasons": [],
        "tasks": [],
        "advices": [],
        "weather_decision": {
            "evidence_quality": "insufficient",
            "admissibility": "refused",
            "reasons": ["selected_window_uncovered"],
            "presentation": {
                "label": "Mission non confirmée",
                "summary": (
                    "La fenêtre calculée dépasse la période couverte par les "
                    "données météo disponibles."
                ),
            },
        },
    }
    assert result.recommendation is recommendation
    assert result.mission is mission


def test_invalid_refused_weather_does_not_infer_target_decision_status():
    decision = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INVALID,
        admissibility=WeatherDecisionAdmissibility.REFUSED,
        reasons=("weather_provider_mismatch",),
    )

    response = TonightResponse.from_result(
        TonightResult(
            night={"date": date(2026, 9, 1)},
            recommendation=None,
            mission=None,
        ),
        weather_decision=decision,
    )

    assert response.target_decision_status is None


def test_weather_refusal_and_transport_status_cannot_diverge():
    refused = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
        admissibility=WeatherDecisionAdmissibility.REFUSED,
        reasons=("selected_window_uncovered",),
    )
    caution = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
        admissibility=WeatherDecisionAdmissibility.CAUTION,
        reasons=("provider_reliability_unavailable",),
    )

    with pytest.raises(ValueError, match="weather_refusal_transport_status_mismatch"):
        TonightResponse(status="available", weather_decision=refused)
    with pytest.raises(ValueError, match="weather_refusal_transport_status_mismatch"):
        TonightResponse(status="weather_refused", weather_decision=caution)


@pytest.mark.parametrize(
    ("admissibility", "label", "summary"),
    [
        (
            WeatherDecisionAdmissibility.ADMISSIBLE,
            "Météo validée pour cette décision",
            "Les preuves météo disponibles permettent de confirmer cette décision.",
        ),
        (
            WeatherDecisionAdmissibility.CAUTION,
            "Validation météo partielle",
            (
                "La mission reste recommandée, mais certaines preuves météo sont "
                "incomplètes ou indisponibles."
            ),
        ),
        (
            WeatherDecisionAdmissibility.REFUSED,
            "Mission non confirmée",
            (
                "Les preuves météo disponibles ne permettent pas de confirmer "
                "cette mission."
            ),
        ),
    ],
)
def test_unknown_weather_reason_uses_only_admissibility_fallback(
    admissibility,
    label,
    summary,
):
    decision = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.SUFFICIENT,
        admissibility=admissibility,
        reasons=("future_weather_reason",),
    )
    result = TonightResult(
        night={"date": date(2026, 9, 1)},
        recommendation=None,
        mission=None,
    )

    response = TonightResponse.from_result(
        result,
        weather_decision=decision,
    ).to_dict()

    assert response["weather_decision"] == {
        "evidence_quality": "sufficient",
        "admissibility": admissibility.value,
        "reasons": ["future_weather_reason"],
        "presentation": {"label": label, "summary": summary},
    }


def test_multiple_weather_reasons_use_admissibility_fallback_without_combining():
    decision = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
        admissibility=WeatherDecisionAdmissibility.CAUTION,
        reasons=("provider_reliability_unavailable", "future_weather_reason"),
    )
    result = TonightResult(
        night={"date": date(2026, 9, 1)},
        recommendation=None,
        mission=None,
    )

    response = TonightResponse.from_result(
        result,
        weather_decision=decision,
    ).to_dict()

    assert response["weather_decision"]["reasons"] == [
        "provider_reliability_unavailable",
        "future_weather_reason",
    ]
    assert response["weather_decision"]["presentation"] == {
        "label": "Validation météo partielle",
        "summary": (
            "La mission reste recommandée, mais certaines preuves météo sont "
            "incomplètes ou indisponibles."
        ),
    }


def make_rejection(catalog_key="M42", score=0.0):
    return CandidateRejection(
        target="Orion",
        catalog_key=catalog_key,
        provenance=CandidateProvenance.DISCOVERY,
        basis=CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE,
        evaluation_score=score,
    )


@pytest.mark.parametrize("count", [0, 1, 4])
def test_rejected_target_mapper_preserves_every_record_in_order(count):
    from decision.services.tonight_rejected_targets import map_rejected_targets

    # Repeated keys and repeated records must survive, including more than two.
    first = make_rejection("Z", -2.5)
    source = (first, make_rejection("A"), make_rejection("Z", -1.0), first)[:count]
    mapped = map_rejected_targets(source)

    assert isinstance(mapped, tuple)
    assert len(mapped) == count
    for entry, rejection in zip(mapped, source):
        assert entry.target == rejection.target
        assert entry.catalog_key == rejection.catalog_key
        assert entry.provenance is rejection.provenance
        assert entry.basis is rejection.basis
        assert entry.evaluation_score == rejection.evaluation_score
        assert entry.target_decision_status is TargetDecisionStatus.NOT_RECOMMENDED


def test_rejected_target_entry_is_immutable_and_status_cannot_be_overridden():
    from decision.services.tonight_rejected_targets import map_rejected_targets

    entry, = map_rejected_targets((make_rejection(),))
    with pytest.raises(FrozenInstanceError):
        entry.target = "changed"
    with pytest.raises(FrozenInstanceError):
        entry.target_decision_status = TargetDecisionStatus.VIABLE
    with pytest.raises(TypeError):
        type(entry)(
            target=entry.target,
            catalog_key=entry.catalog_key,
            provenance=entry.provenance,
            basis=entry.basis,
            evaluation_score=entry.evaluation_score,
            target_decision_status=TargetDecisionStatus.VIABLE,
        )


@pytest.mark.parametrize("value", [None, {}, make_candidate()])
def test_rejected_target_mapper_accepts_only_candidate_rejection_records(value):
    from decision.services.tonight_rejected_targets import map_rejected_targets

    with pytest.raises(TypeError):
        map_rejected_targets((value,))


@pytest.mark.parametrize("status", [
    TonightStatus.NO_CANDIDATE,
    TonightStatus.NO_RECOMMENDATION,
    TonightStatus.NO_MISSION,
    TonightStatus.NO_PRODUCTIVE_WINDOW,
    TonightStatus.AVAILABLE,
])
@pytest.mark.parametrize("refused", [False, True])
def test_rejections_are_serialized_without_changing_existing_decisions(status, refused):
    from decision.services.tonight_rejected_targets import map_rejected_targets

    candidate = make_candidate(decision_score=None, final_score=None)
    shortlist = (make_candidate(catalog_key="M33"), make_candidate(catalog_key="M42"))
    recommendation = Recommendation(
        opportunity=Opportunity(
            action=Action.START_PROJECT,
            candidate=candidate,
            shortlist_entries=shortlist,
        ),
        confidence=None,
    ) if status not in {TonightStatus.NO_CANDIDATE, TonightStatus.NO_RECOMMENDATION} else None
    result = TonightResult(
        night=None,
        recommendation=recommendation,
        mission=None,
        status=status,
        candidate_rejections=(make_rejection(),),
    )
    weather = WeatherTrustDecision(
        evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
        admissibility=WeatherDecisionAdmissibility.REFUSED,
        reasons=("selected_window_uncovered",),
    ) if refused else None
    kwargs = dict(
        weather_decision=weather,
        viable_shortlist_catalog_keys=set(),
        selected_alternatives=(),
    )
    # Raw records, absent scores/assessment/mission, and non-viable shortlist
    # entries cannot cause serialization to assign rejection status itself.
    baseline = TonightResponse.from_result(result, **kwargs).to_dict()
    assert baseline["rejected_targets"] == []
    response = TonightResponse.from_result(
        result,
        rejected_targets=map_rejected_targets(result.candidate_rejections),
        **kwargs,
    ).to_dict()
    assert response.pop("rejected_targets") == [{
        "target": "Orion",
        "catalog_key": "M42",
        "provenance": "discovery",
        "basis": "non_positive_evaluation_score",
        "evaluation_score": 0.0,
        "target_decision_status": "not_recommended",
    }]
    baseline.pop("rejected_targets")
    assert response == baseline
    assert result.recommendation is recommendation


def test_rejected_target_list_defaults_are_independent():
    first = TonightResponse(status="no_candidate")
    second = TonightResponse(status="no_candidate")
    assert first.rejected_targets == second.rejected_targets == []
    assert first.rejected_targets is not second.rejected_targets


@pytest.mark.parametrize("quality", list(WeatherEvidenceQuality))
@pytest.mark.parametrize("admissibility", list(WeatherDecisionAdmissibility))
def test_target_insufficiency_requires_explicit_insufficient_refusal(quality, admissibility):
    from decision.services.candidate_assessment import CandidateAssessment
    from decision.services.tonight_target_evidence import (
        qualify_candidate_evidence_insufficiency,
        qualify_primary_evidence_insufficiency,
    )

    candidate = make_candidate(decision_score=None, final_score=None)
    reasons = ("selected_window_uncovered", "original_reason", "original_reason")
    decision = WeatherTrustDecision(quality, admissibility, reasons)
    assessment = CandidateAssessment(productive_window=None, weather_decision=decision)
    records = (
        qualify_candidate_evidence_insufficiency(candidate=candidate, assessment=assessment),
        qualify_primary_evidence_insufficiency(candidate=candidate, weather_decision=decision),
    )
    qualifies = (
        quality is WeatherEvidenceQuality.INSUFFICIENT
        and admissibility is WeatherDecisionAdmissibility.REFUSED
    )
    for record in records:
        if not qualifies:
            assert record is None
            continue
        assert [f.name for f in fields(record)] == [
            "target", "catalog_key", "provenance", "weather_decision",
        ]
        assert record.target == candidate.name
        assert record.catalog_key == candidate.catalog_key
        assert record.provenance is candidate.provenance
        assert record.weather_decision is decision
        assert record.weather_decision.reasons is reasons
        with pytest.raises(FrozenInstanceError):
            record.target = "changed"


def test_target_insufficiency_requires_typed_identity_and_assessment():
    from decision.services.candidate_assessment import CandidateAssessment
    from decision.services.tonight_target_evidence import (
        qualify_candidate_evidence_insufficiency,
        qualify_primary_evidence_insufficiency,
    )

    candidate = make_candidate()
    decision = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT,
        WeatherDecisionAdmissibility.REFUSED,
        ("selected_window_uncovered",),
    )
    assessment = CandidateAssessment(productive_window=None, weather_decision=decision)
    assert qualify_candidate_evidence_insufficiency(candidate=candidate, assessment=None) is None
    assert qualify_primary_evidence_insufficiency(candidate=candidate, weather_decision=None) is None
    for invalid_candidate in (None, make_rejection(), {"catalog_key": "M42"}):
        with pytest.raises(TypeError):
            qualify_candidate_evidence_insufficiency(
                candidate=invalid_candidate, assessment=assessment,
            )
    for invalid_assessment in (make_rejection(), decision, {"weather_decision": decision}):
        with pytest.raises(TypeError):
            qualify_candidate_evidence_insufficiency(
                candidate=candidate, assessment=invalid_assessment,
            )


def test_target_insufficiency_record_rejects_nonqualifying_weather():
    from decision.models.target_evidence_insufficiency import TargetEvidenceInsufficiency

    for quality, admissibility in (
        (WeatherEvidenceQuality.INSUFFICIENT, WeatherDecisionAdmissibility.CAUTION),
        (WeatherEvidenceQuality.INVALID, WeatherDecisionAdmissibility.REFUSED),
        (WeatherEvidenceQuality.SUFFICIENT, WeatherDecisionAdmissibility.REFUSED),
    ):
        with pytest.raises(ValueError):
            TargetEvidenceInsufficiency(
                target="Orion", catalog_key="M42", provenance=CandidateProvenance.DISCOVERY,
                weather_decision=WeatherTrustDecision(quality, admissibility, ()),
            )


@pytest.mark.parametrize("refused", [False, True])
def test_target_insufficiency_transport_only_serializes_supplied_entries(refused):
    from decision.services.tonight_target_evidence import (
        map_target_evidence_insufficiencies,
        qualify_primary_evidence_insufficiency,
    )

    decision = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT,
        WeatherDecisionAdmissibility.REFUSED,
        ("selected_window_uncovered", "second_reason", "second_reason"),
    )
    record = qualify_primary_evidence_insufficiency(
        candidate=make_candidate(), weather_decision=decision,
    )
    entries = map_target_evidence_insufficiencies((record, record))
    assert entries[0].weather_decision is decision
    assert entries[0].target_decision_status is TargetDecisionStatus.INSUFFICIENT_EVIDENCE
    with pytest.raises(FrozenInstanceError):
        entries[0].target_decision_status = TargetDecisionStatus.VIABLE
    with pytest.raises(TypeError):
        type(entries[0])(
            target=record.target, catalog_key=record.catalog_key,
            provenance=record.provenance, weather_decision=decision,
            target_decision_status=TargetDecisionStatus.VIABLE,
        )
    result = TonightResult(None, None, None, status=TonightStatus.NO_RECOMMENDATION)
    weather = decision if refused else None
    baseline = TonightResponse.from_result(result, weather_decision=weather).to_dict()
    assert baseline.pop("insufficient_evidence_targets") == []
    response = TonightResponse.from_result(
        result, weather_decision=weather, insufficient_evidence_targets=entries,
    ).to_dict()
    assert response.pop("insufficient_evidence_targets") == [{
        "target": "Andromeda", "catalog_key": "M31", "provenance": "project",
        "weather_decision": {
            "evidence_quality": "insufficient", "admissibility": "refused",
            "reasons": list(decision.reasons),
        },
        "target_decision_status": "insufficient_evidence",
    }] * 2
    assert response == baseline
    with pytest.raises(TypeError):
        map_target_evidence_insufficiencies((make_rejection(),))
