from __future__ import annotations

import pytest
from app import create_app
from app.algorithms.bayesian_network import (
    DEFAULT_CPT,
    DEFAULT_PRIORS,
    DELAY_RISK_STATES,
    DISTANCE_STATES,
    DURATION_STATES,
    PRIORITY_STATES,
    TIME_SLOT_STATES,
    BayesianDelayNetwork,
    build_bayesian_network,
    categorize_distance,
    categorize_priority,
    categorize_time_slot,
    categorize_visit_duration,
    get_bayesian_network,
    predict_route_delays,
    predict_visit_delay,
    validate_cpts,
)


def test_bayesian_network_structure():
    bn = get_bayesian_network()
    info = bn.get_structure_info()
    assert info["topology"]["totalCptConfigurations"] == 54
    assert len(info["topology"]["edges"]) == 4
    parent_ids = [n["id"] for n in info["topology"]["nodes"] if n["type"] == "parent"]
    assert set(parent_ids) == {"Distance", "VisitDuration", "TimeSlot", "Priority"}
    target = next(n for n in info["topology"]["nodes"] if n["type"] == "target")
    assert target["id"] == "DelayRisk"
    assert target["parents"] == ["Distance", "VisitDuration", "TimeSlot", "Priority"]


def test_cpt_probability_validation():
    assert validate_cpts() is True
    # Test that mutating a row to not sum to 1.0 fails validation
    bad_cpt = dict(DEFAULT_CPT)
    bad_cpt[("Near", "Short", "Morning", "Low")] = {"Low": 0.5, "Medium": 0.5, "High": 0.5}
    with pytest.raises(ValueError, match="does not sum to 1.0"):
        validate_cpts(bad_cpt)


def test_prior_probability_validation():
    for name, dist in DEFAULT_PRIORS.items():
        total = sum(dist.values())
        assert abs(total - 1.0) < 1e-5
        for st, p in dist.items():
            assert 0.0 <= p <= 1.0

    bad_priors = {**DEFAULT_PRIORS, "Distance": {"Near": 0.5, "Medium": 0.5, "Far": 0.5}}
    with pytest.raises(ValueError, match="Prior for Distance does not sum to 1.0"):
        validate_cpts(priors=bad_priors)


def test_distance_categorization():
    assert categorize_distance(0.0) == "Near"
    assert categorize_distance(4.99) == "Near"
    assert categorize_distance(5.0) == "Medium"
    assert categorize_distance(10.5) == "Medium"
    assert categorize_distance(15.0) == "Medium"
    assert categorize_distance(15.01) == "Far"
    assert categorize_distance(50.0) == "Far"

    with pytest.raises(ValueError):
        categorize_distance(None)
    with pytest.raises(ValueError):
        categorize_distance("invalid")


def test_visit_duration_categorization():
    assert categorize_visit_duration(15) == "Short"
    assert categorize_visit_duration(29) == "Short"
    assert categorize_visit_duration(30) == "Medium"
    assert categorize_visit_duration(45) == "Medium"
    assert categorize_visit_duration(59) == "Medium"
    assert categorize_visit_duration(60) == "Long"
    assert categorize_visit_duration(120) == "Long"

    with pytest.raises(ValueError):
        categorize_visit_duration(None)


def test_time_slot_categorization():
    assert categorize_time_slot("08:00") == "Morning"
    assert categorize_time_slot("09:30") == "Morning"
    assert categorize_time_slot("12:29") == "Morning"
    assert categorize_time_slot("12:30") == "Afternoon"
    assert categorize_time_slot("14:45") == "Afternoon"
    assert categorize_time_slot("2026-11-20T10:15:00Z") == "Morning"
    assert categorize_time_slot("2026-11-20T15:30:00Z") == "Afternoon"

    with pytest.raises(ValueError):
        categorize_time_slot(None)


def test_priority_categorization():
    assert categorize_priority(1) == "Low"
    assert categorize_priority(2) == "Low"
    assert categorize_priority(3) == "Medium"
    assert categorize_priority(4) == "High"
    assert categorize_priority(5) == "High"
    assert categorize_priority("Low") == "Low"
    assert categorize_priority("high") == "High"

    with pytest.raises(ValueError):
        categorize_priority(None)


def test_posterior_probabilities_sum_to_one_across_all_cpt_permutations():
    bn = get_bayesian_network()
    for dist in DISTANCE_STATES:
        for dur in DURATION_STATES:
            for ts in TIME_SLOT_STATES:
                for prio in PRIORITY_STATES:
                    probs = bn.infer_posterior(
                        {"Distance": dist, "VisitDuration": dur, "TimeSlot": ts, "Priority": prio}
                    )
                    assert set(probs.keys()) == set(DELAY_RISK_STATES)
                    assert abs(sum(probs.values()) - 1.0) < 1e-4
                    for v in probs.values():
                        assert 0.0 <= v <= 1.0


def test_posterior_monotonicity_low_vs_high_risk():
    bn = get_bayesian_network()
    low_res = bn.predict_visit(
        distributor_id="d1",
        distributor_name="Best Case",
        distance_category="Near",
        visit_duration_category="Short",
        time_slot="Morning",
        priority_category="Low",
    )
    assert low_res["predictedRisk"] == "Low"
    assert low_res["probabilities"]["Low"] > 0.80

    high_res = bn.predict_visit(
        distributor_id="d2",
        distributor_name="Worst Case",
        distance_category="Far",
        visit_duration_category="Long",
        time_slot="Afternoon",
        priority_category="High",
    )
    assert high_res["predictedRisk"] == "High"
    assert high_res["probabilities"]["High"] > 0.80
    assert high_res["recommendedBufferMinutes"] >= 10


def test_missing_and_invalid_evidence():
    bn = get_bayesian_network()
    with pytest.raises(ValueError, match="Missing required Bayesian Network evidence"):
        bn.predict_visit(
            distributor_id="d-none",
            distributor_name="Missing Evidence",
            distance_km=None,
            visit_duration_minutes=None,
        )


def test_predict_route_delays_helper():
    stops = [
        {
            "distributorId": "d1",
            "distributorName": "Stop 1",
            "distanceKm": 3.0,
            "visitDurationMinutes": 25,
            "estimatedArrival": "09:30",
            "priority": 2,
        },
        {
            "distributorId": "d2",
            "distributorName": "Stop 2",
            "distanceKm": 18.0,
            "visitDurationMinutes": 65,
            "estimatedArrival": "14:00",
            "priority": 5,
        },
    ]
    results = predict_route_delays(stops)
    assert len(results) == 2
    assert results[0]["predictedRisk"] == "Low"
    assert results[1]["predictedRisk"] == "High"


def test_api_predictions_endpoints():
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.test_client() as client:
        # 1. Model Info
        info_res = client.get("/api/predictions/model-info")
        assert info_res.status_code == 200
        info_json = info_res.get_json()
        assert info_json["success"] is True
        assert info_json["data"]["modelVersion"] == "1.0.0-illustrative"
        assert len(info_json["data"]["variables"]) == 5

        # 2. CPT Data
        cpt_res = client.get("/api/predictions/cpt")
        assert cpt_res.status_code == 200
        cpt_json = cpt_res.get_json()
        assert cpt_json["success"] is True
        assert cpt_json["data"]["totalRows"] == 54

        # 3. Visit Delay Prediction POST (full evidence)
        pred_res = client.post(
            "/api/predictions/visit-delay",
            json={
                "distributorName": "API Test Outlet",
                "distanceKm": 8.0,
                "visitDurationMinutes": 45,
                "timeSlot": "11:00",
                "priority": 3,
            },
        )
        assert pred_res.status_code == 200
        pred_json = pred_res.get_json()
        assert pred_json["success"] is True
        assert "predictedRisk" in pred_json["data"]
        assert "probabilities" in pred_json["data"]
        assert abs(sum(pred_json["data"]["probabilities"].values()) - 1.0) < 1e-4

        # 4. Partial evidence marginalization via API
        partial_res = client.post(
            "/api/predictions/visit-delay",
            json={
                "distributorName": "Partial API Stop",
                "distanceCategory": "Far",
                "timeSlot": "Afternoon",
                "allowPartial": True,
            },
        )
        assert partial_res.status_code == 200
        partial_data = partial_res.get_json()["data"]
        assert partial_data["isPartialEvidence"] is True
        assert set(partial_data["marginalizedVariables"]) == {"VisitDuration", "Priority"}
        assert partial_data["evidence"]["visitDurationCategory"] == "Unobserved"
        assert partial_data["evidence"]["priorityCategory"] == "Unobserved"
        assert abs(sum(partial_data["probabilities"].values()) - 1.0) < 1e-4


def test_partial_evidence_marginalization_matches_prior_weighting():
    bn = get_bayesian_network()
    res = bn.predict_visit(
        distributor_id=None,
        distributor_name="Partial Stop",
        distance_category="Far",
        time_slot="Afternoon",
        allow_partial=True,
    )
    assert res["isPartialEvidence"] is True
    assert set(res["marginalizedVariables"]) == {"VisitDuration", "Priority"}
    assert res["evidence"]["visitDurationCategory"] == "Unobserved"
    assert res["evidence"]["priorityCategory"] == "Unobserved"
    assert abs(sum(res["probabilities"].values()) - 1.0) < 1e-4

    # All-unobserved must still raise even with allow_partial=True
    with pytest.raises(ValueError, match="At least one Bayesian Network evidence variable"):
        bn.predict_visit(
            distributor_id=None,
            distributor_name="All Empty",
            allow_partial=True,
        )

