from __future__ import annotations

import json
import pytest

from app import create_app


@pytest.fixture()
def client_no_db():
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.test_client() as client:
        yield client


def test_health_reports_disconnected_without_leaking_secrets(client_no_db):
    res = client_no_db.get("/api/health")
    assert res.status_code == 503
    body = res.get_json()
    assert body["success"] is False
    assert body["data"]["app"] == "ok"
    assert body["data"]["database"]["configured"] is False
    assert body["data"]["database"]["connected"] is False
    assert body["error"]["code"] == "DATABASE_NOT_CONFIGURED"
    raw = json.dumps(body)
    assert "postgres://" not in raw
    assert "postgresql://" not in raw


def test_db_endpoints_return_503_when_unconfigured(client_no_db):
    for path in ["/api/distributors", "/api/office", "/api/route-plans", "/api/analytics/summary"]:
        res = client_no_db.get(path)
        assert res.status_code == 503
        body = res.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "DATABASE_NOT_CONFIGURED"


def test_unknown_api_endpoint_returns_structured_404(client_no_db):
    res = client_no_db.get("/api/nonexistent")
    assert res.status_code == 404
    body = res.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "API_NOT_FOUND"


def test_invalid_uuid_rejected_with_400():
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.test_client() as client:
        res = client.get("/api/distributors/not-a-uuid")
        assert res.status_code == 400
        body = res.get_json()
        assert body["error"]["code"] == "INVALID_ID"

        res2 = client.put("/api/office/bad-id", json={})
        assert res2.status_code == 400
        assert res2.get_json()["error"]["code"] == "INVALID_ID"

        res3 = client.post(
            "/api/distributors",
            json={
                "name": "Test",
                "contact_person": "Jane",
                "phone": "123",  # too short
                "address": "Shahrah-e-Faisal, Karachi",
                "latitude": 95.0,  # out of bounds
                "longitude": 67.0,
                "priority": 3,
                "visit_duration_minutes": 30,
                "opening_time": "17:00",
                "closing_time": "09:00",
            },
        )
        assert res3.status_code == 400
        assert res3.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_end_to_end_sqlite_workflows(tmp_path):
    db_file = tmp_path / "integration.db"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        }
    )

    with app.test_client() as client:
        # 1. Health & Schema Init
        init_res = client.post("/api/db/init")
        assert init_res.status_code == 200
        assert init_res.get_json()["data"]["database"]["schemaReady"] is True

        health_res = client.get("/api/health")
        assert health_res.status_code == 200
        assert health_res.get_json()["data"]["database"]["connected"] is True

        # 2. Invalid query params return 400 VALIDATION_ERROR / INVALID_ID
        bad_page = client.get("/api/distributors?page=abc")
        assert bad_page.status_code == 400
        assert bad_page.get_json()["error"]["code"] == "VALIDATION_ERROR"

        bad_hist = client.get("/api/predictions/visit-delay/history?routePlanId=bad-uuid")
        assert bad_hist.status_code == 400
        assert bad_hist.get_json()["error"]["code"] == "INVALID_ID"

        # 3. Load Karachi demo data & verify CSV export formula neutralization
        demo_res = client.post("/api/demo/load")
        assert demo_res.status_code == 201
        dist_list = client.get("/api/distributors?pageSize=20").get_json()["data"]["items"]
        assert len(dist_list) == 9
        dist_ids = [d["id"] for d in dist_list]

        formula_dist = client.post(
            "/api/distributors",
            json={
                "name": "=CMD|'/C calc'!A0",
                "contact_person": "+Evil",
                "phone": "+923001234567",
                "address": "PECHS Karachi",
                "latitude": 24.87,
                "longitude": 67.07,
                "priority": 2,
                "visit_duration_minutes": 25,
                "opening_time": "09:00",
                "closing_time": "17:00",
            },
        )
        assert formula_dist.status_code == 201
        csv_res = client.get("/api/distributors/export")
        assert csv_res.status_code == 200
        csv_text = csv_res.get_data(as_text=True)
        assert "'=CMD|'/C calc'!A0" in csv_text
        assert "'+Evil" in csv_text
        client.delete(f"/api/distributors/{formula_dist.get_json()['data']['id']}")

        off_res = client.get("/api/office").get_json()["data"]
        assert len(off_res["offices"]) == 1
        office_id = off_res["offices"][0]["id"]
        assert off_res["offices"][0]["name"] == "Karachi Central Hub (Demo)"

        # 4. K-Means clustering + real Haversine distanceToCentroidKm
        cl_res = client.post(
            "/api/clusters/run",
            json={"distributorIds": dist_ids, "k": 3, "seed": 42, "maxIterations": 100, "initMethod": "kmeans++"},
        )
        assert cl_res.status_code == 200
        latest_cl = client.get("/api/clusters/latest").get_json()["data"]
        assert len(latest_cl["centroids"]) == 3
        assert any(a["distanceToCentroidKm"] > 0 for a in latest_cl["assignments"])

        # 5. CSP Scheduler with officeId + Bayesian advisory
        sched_res = client.post(
            "/api/schedules/run",
            json={
                "distributorIds": dist_ids[:5],
                "officeId": office_id,
                "scheduleDate": "2026-11-22",
                "workStartTime": "09:00",
                "workEndTime": "17:00",
                "slotIncrementMinutes": 15,
                "travelBufferMinutes": 15,
                "lunchBreakEnabled": True,
                "lunchStartTime": "12:30",
                "lunchDurationMinutes": 60,
                "maxVisitsPerDay": 8,
            },
        )
        assert sched_res.status_code == 200
        sched_data = sched_res.get_json()["data"]
        assert sched_data["officeId"] == office_id
        assert len(sched_data["scheduled"]) >= 1
        assert "delayRisk" in sched_data["scheduled"][0]

        latest_sched = client.get("/api/schedules/latest").get_json()["data"]
        assert latest_sched["officeId"] == office_id
        assert "bayesianAdvisory" in latest_sched

        # 6. Preview Optimization with custom user parameters + per-algorithm BN reports
        opt_res = client.post(
            "/api/optimize/preview",
            json={
                "officeId": office_id,
                "distributorIds": dist_ids[:5],
                "seed": 99,
                "distanceMultiplier": 1.3,
                "travelMode": "simulated_van",
                "returnToOffice": True,
                "gaPopulationSize": 40,
                "gaGenerations": 50,
                "gaMutationRate": 0.25,
            },
        )
        assert opt_res.status_code == 200
        opt_data = opt_res.get_json()["data"]
        assert opt_data["appliedConfig"]["seed"] == 99
        assert opt_data["appliedConfig"]["distanceMultiplier"] == 1.3
        assert opt_data["appliedConfig"]["gaPopulationSize"] == 40
        assert set(["BFS", "UCS", "A*", "GENETIC_ALGORITHM"]).issubset(
            set(opt_data["delayPredictionsByAlgorithm"].keys())
        )

        # 7. Save Route Plan + Optimize + Switch Algorithm refreshes BN predictions
        create_plan = client.post(
            "/api/route-plans",
            json={
                "name": "Karachi Integration Plan",
                "planDate": "2026-11-22",
                "officeId": office_id,
                "distributorIds": dist_ids[:5],
                "travelMode": "simulated_vehicle",
                "returnToOffice": True,
                "distanceMultiplier": 1.2,
                "graphSeed": 42,
            },
        )
        assert create_plan.status_code == 201
        plan_id = create_plan.get_json()["data"]["id"]

        run_opt = client.post(
            f"/api/route-plans/{plan_id}/optimize",
            json={
                "distributorIds": dist_ids[:5],
                "selectedAlgorithm": "A*",
                "seed": 42,
                "distanceMultiplier": 1.2,
                "gaPopulationSize": 40,
                "gaGenerations": 50,
                "gaMutationRate": 0.18,
            },
        )
        assert run_opt.status_code == 200

        switch_res = client.put(f"/api/route-plans/{plan_id}", json={"selectedAlgorithm": "BFS"})
        assert switch_res.status_code == 200
        assert switch_res.get_json()["data"]["selected_algorithm"] == "BFS"

        # 8. Analytics excludes synthetic workspace plans, counts only real route plans
        analytics = client.get("/api/analytics/summary").get_json()["data"]
        assert analytics["counts"]["totalRoutePlans"] == 1
        assert analytics["counts"]["totalOffices"] == 1
        assert analytics["delayPredictionSummary"]["totalPredictions"] >= 1

        # 9. Office DELETE returns 409 when referenced by a saved route plan, succeeds for unreferenced office
        del_conflict = client.delete(f"/api/office/{office_id}")
        assert del_conflict.status_code == 409
        assert del_conflict.get_json()["error"]["code"] == "OFFICE_IN_USE"

        extra_office = client.post(
            "/api/office",
            json={
                "name": "Temporary Depot",
                "address": "PECHS Karachi",
                "latitude": 24.87,
                "longitude": 67.07,
                "is_default": False,
            },
        )
        assert extra_office.status_code == 201
        extra_id = extra_office.get_json()["data"]["id"]
        del_ok = client.delete(f"/api/office/{extra_id}")
        assert del_ok.status_code == 200

