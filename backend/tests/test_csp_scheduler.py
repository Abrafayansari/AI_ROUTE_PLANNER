from __future__ import annotations

from types import SimpleNamespace

from app import create_app
from app.algorithms import run_csp_scheduler
from app.utils.metrics import time_to_minutes


def _assert_csp_invariants(result: dict, dists_by_id: dict[str, dict], cfg: dict) -> None:
    work_start = time_to_minutes(cfg["workStartTime"])
    work_end = time_to_minutes(cfg["workEndTime"])
    lunch_enabled = bool(cfg.get("lunchBreakEnabled", True))
    lunch_start = time_to_minutes(cfg.get("lunchStartTime", "12:30"))
    lunch_end = lunch_start + int(cfg.get("lunchDurationMinutes", 60))
    max_visits = int(cfg.get("maxVisitsPerDay", 10))
    office_map = cfg.get("officeToDistributorMinutes") or {}
    travel_matrix = cfg.get("travelTimesMatrix") or {}
    buffer_min = int(cfg.get("travelBufferMinutes", 15))

    scheduled = result["scheduled"]
    assert len(scheduled) <= max_visits

    for idx, entry in enumerate(scheduled):
        did = entry["distributorId"]
        orig = dists_by_id[did]
        open_m = time_to_minutes(orig["openingTime"])
        close_m = time_to_minutes(orig["closingTime"])
        dur = int(orig["visitDurationMinutes"])

        assert entry["startMinutes"] >= work_start
        assert entry["endMinutes"] == entry["startMinutes"] + dur
        assert entry["endMinutes"] <= work_end
        assert entry["startMinutes"] >= open_m
        assert entry["endMinutes"] <= close_m

        if lunch_enabled:
            assert not (entry["startMinutes"] < lunch_end and lunch_start < entry["endMinutes"])

        if idx == 0:
            expected_office_travel = int(office_map[did]) if did in office_map else (buffer_min if buffer_min > 0 else 15)
            assert entry["startMinutes"] >= work_start + expected_office_travel
        else:
            prev_did = scheduled[idx - 1]["distributorId"]
            prev_end = scheduled[idx - 1]["endMinutes"]
            expected_travel = (
                int(travel_matrix[prev_did][did])
                if prev_did in travel_matrix and did in travel_matrix[prev_did]
                else (buffer_min if buffer_min > 0 else 15)
            )
            assert prev_end + expected_travel <= entry["startMinutes"]


def test_office_to_first_stop_45m_prevents_0900_start_and_enforces_feasibility():
    # Bug 1 regression: 45m travel from office at 09:00 means first visit cannot start before 09:45.
    distributors = [
        {
            "id": "d-early",
            "name": "Far North Outlet",
            "priority": 5,
            "visitDurationMinutes": 30,
            "openingTime": "09:00",
            "closingTime": "12:00",
        }
    ]
    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,
        "travelBufferMinutes": 0,
        "lunchBreakEnabled": False,
        "maxVisitsPerDay": 8,
        "useRoadTravelTimes": True,
        "officeToDistributorMinutes": {"d-early": 45},
    }
    res = run_csp_scheduler(distributors, cfg)
    assert len(res["scheduled"]) == 1
    first = res["scheduled"][0]
    assert first["startTime"] == "09:45"
    assert first["startMinutes"] >= time_to_minutes("09:00") + 45
    assert first["travelMinutesFromPrevious"] == 45
    _assert_csp_invariants(res, {d["id"]: d for d in distributors}, cfg)

    # If the distributor closes at 10:00, a 30m visit arriving at 09:45 ends at 10:15 > 10:00 -> infeasible!
    tight_dist = [
        {
            "id": "d-too-early",
            "name": "Short Morning Window",
            "priority": 5,
            "visitDurationMinutes": 30,
            "openingTime": "09:00",
            "closingTime": "10:00",
        }
    ]
    res_tight = run_csp_scheduler(tight_dist, {**cfg, "officeToDistributorMinutes": {"d-too-early": 45}})
    assert len(res_tight["scheduled"]) == 0
    assert len(res_tight["unscheduled"]) == 1
    assert "45m" in res_tight["unscheduled"][0]["reason"]
    assert "office" in res_tight["unscheduled"][0]["reason"].lower()


def test_missing_routing_data_does_not_assume_zero_office_travel():
    # When routing data is missing (even if travelBufferMinutes=0 and useRoadTravelTimes omitted/True),
    # CSP must NOT assume 0 minutes of office-to-first-stop travel.
    distributors = [
        {
            "id": "d-missing",
            "name": "Unmapped Stop",
            "priority": 4,
            "visitDurationMinutes": 30,
            "openingTime": "09:00",
            "closingTime": "12:00",
        }
    ]
    res = run_csp_scheduler(
        distributors,
        {
            "workStartTime": "09:00",
            "workEndTime": "17:00",
            "slotIncrementMinutes": 15,
            "travelBufferMinutes": 0,
            "lunchBreakEnabled": False,
            "maxVisitsPerDay": 5,
        },
    )
    assert len(res["scheduled"]) == 1
    first = res["scheduled"][0]
    assert first["startMinutes"] > time_to_minutes("09:00")
    assert first["travelMinutesFromPrevious"] > 0


def test_high_priority_distributor_not_ignored_for_narrow_low_priority():
    # Bug 2 regression: Low-priority distributor with smaller domain (2 slots) vs High-priority
    # distributor with wide domain (25+ slots) under maxVisitsPerDay=1 must schedule High-priority.
    distributors = [
        {
            "id": "d-low",
            "name": "Narrow Low Priority",
            "priority": 1,
            "visitDurationMinutes": 45,
            "openingTime": "09:00",
            "closingTime": "10:00",
        },
        {
            "id": "d-high",
            "name": "Wide High Priority",
            "priority": 5,
            "visitDurationMinutes": 45,
            "openingTime": "09:00",
            "closingTime": "17:00",
        },
    ]
    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
        "maxVisitsPerDay": 1,
    }
    res = run_csp_scheduler(distributors, cfg)
    assert len(res["scheduled"]) == 1
    assert res["scheduled"][0]["distributorId"] == "d-high"
    assert len(res["unscheduled"]) == 1
    assert res["unscheduled"][0]["distributorId"] == "d-low"
    assert "cap" in res["unscheduled"][0]["reason"].lower()
    _assert_csp_invariants(res, {d["id"]: d for d in distributors}, cfg)


def test_nine_distributors_with_cap_eight_prefers_higher_priorities():
    # Reproduces the exact 9-distributor priority inversion where P2 previously beat P4.
    distributors = [
        {"id": "1", "name": "Northgate P5", "priority": 5, "visitDurationMinutes": 35, "openingTime": "08:00", "closingTime": "14:00"},
        {"id": "2", "name": "Riverside P5", "priority": 5, "visitDurationMinutes": 45, "openingTime": "09:00", "closingTime": "15:30"},
        {"id": "3", "name": "Cedar Ridge P4", "priority": 4, "visitDurationMinutes": 30, "openingTime": "09:00", "closingTime": "17:00"},
        {"id": "4", "name": "Eastside P4", "priority": 4, "visitDurationMinutes": 40, "openingTime": "08:30", "closingTime": "16:30"},
        {"id": "5", "name": "TechRidge P4", "priority": 4, "visitDurationMinutes": 35, "openingTime": "08:00", "closingTime": "16:00"},
        {"id": "6", "name": "Southpark P3", "priority": 3, "visitDurationMinutes": 30, "openingTime": "10:00", "closingTime": "18:00"},
        {"id": "7", "name": "Westlake P3", "priority": 3, "visitDurationMinutes": 25, "openingTime": "09:30", "closingTime": "17:30"},
        {"id": "8", "name": "Barton Creek P2", "priority": 2, "visitDurationMinutes": 30, "openingTime": "11:00", "closingTime": "19:00"},
        {"id": "9", "name": "Mueller P2", "priority": 2, "visitDurationMinutes": 25, "openingTime": "10:00", "closingTime": "18:00"},
    ]
    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
        "maxVisitsPerDay": 8,
        "officeToDistributorMinutes": {"1": 45, **{str(i): 15 for i in range(2, 10)}},
    }
    res = run_csp_scheduler(distributors, cfg)
    assert len(res["scheduled"]) == 8
    scheduled_ids = {s["distributorId"] for s in res["scheduled"]}
    # All P5, P4, P3 accounts must be scheduled; only one P2 account may remain unscheduled
    assert {"1", "2", "3", "4", "5", "6", "7"}.issubset(scheduled_ids)
    assert len(res["unscheduled"]) == 1
    assert res["unscheduled"][0]["priority"] == 2
    # Northgate (id "1") has 45m office travel, so it cannot start before 09:45 if first
    assert res["scheduled"][0]["startMinutes"] >= time_to_minutes("09:00") + (
        45 if res["scheduled"][0]["distributorId"] == "1" else 15
    )
    _assert_csp_invariants(res, {d["id"]: d for d in distributors}, cfg)


def test_infeasible_high_priority_does_not_block_feasible_distributors():
    # Infeasible P5s (outside hours + blocked by lunch + unreachable after 45m office travel)
    # must be cleanly rejected while all feasible lower-priority stops get scheduled.
    distributors = [
        {
            "id": "p5-afterhours",
            "name": "Night Key Account",
            "priority": 5,
            "visitDurationMinutes": 45,
            "openingTime": "18:00",
            "closingTime": "21:00",
        },
        {
            "id": "p5-lunch-blocked",
            "name": "Lunch-Only Key Account",
            "priority": 5,
            "visitDurationMinutes": 45,
            "openingTime": "12:30",
            "closingTime": "13:30",
        },
        {
            "id": "p5-far-morning",
            "name": "Far Morning Key Account",
            "priority": 5,
            "visitDurationMinutes": 45,
            "openingTime": "09:00",
            "closingTime": "10:15",
        },
        {
            "id": "p3-ok",
            "name": "Midday Distributor",
            "priority": 3,
            "visitDurationMinutes": 40,
            "openingTime": "09:00",
            "closingTime": "16:00",
        },
        {
            "id": "p1-ok",
            "name": "Afternoon Distributor",
            "priority": 1,
            "visitDurationMinutes": 35,
            "openingTime": "13:30",
            "closingTime": "17:00",
        },
    ]
    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
        "maxVisitsPerDay": 5,
        "useRoadTravelTimes": True,
        "officeToDistributorMinutes": {
            "p5-afterhours": 10,
            "p5-lunch-blocked": 10,
            "p5-far-morning": 45,  # arrives 09:45 + 45m = 10:30 > 10:15 closing
            "p3-ok": 15,
            "p1-ok": 20,
        },
        "travelTimesMatrix": {
            "p3-ok": {"p1-ok": 25},
            "p1-ok": {"p3-ok": 25},
        },
    }
    res = run_csp_scheduler(distributors, cfg)
    scheduled_ids = [s["distributorId"] for s in res["scheduled"]]
    assert scheduled_ids == ["p3-ok", "p1-ok"]

    unscheduled_by_id = {u["distributorId"]: u for u in res["unscheduled"]}
    assert set(unscheduled_by_id.keys()) == {"p5-afterhours", "p5-lunch-blocked", "p5-far-morning"}
    assert "opening hours" in unscheduled_by_id["p5-afterhours"]["reason"].lower()
    assert "lunch" in unscheduled_by_id["p5-lunch-blocked"]["reason"].lower()
    assert "45m" in unscheduled_by_id["p5-far-morning"]["reason"].lower()
    _assert_csp_invariants(res, {d["id"]: d for d in distributors}, cfg)


def test_multiple_priorities_and_windows_maximize_priority_respecting_travel_and_lunch():
    # Multiple priorities and overlapping morning windows + afternoon windows + directed O-D matrix
    distributors = [
        {"id": "d-p5-morning", "name": "Alpha P5", "priority": 5, "visitDurationMinutes": 45, "openingTime": "09:30", "closingTime": "11:00"},
        {"id": "d-p2-morning", "name": "Beta P2", "priority": 2, "visitDurationMinutes": 45, "openingTime": "09:30", "closingTime": "11:00"},
        {"id": "d-p4-flex", "name": "Gamma P4", "priority": 4, "visitDurationMinutes": 45, "openingTime": "09:00", "closingTime": "16:30"},
        {"id": "d-p3-aft", "name": "Delta P3", "priority": 3, "visitDurationMinutes": 45, "openingTime": "13:30", "closingTime": "17:00"},
    ]
    # d-p5-morning and d-p2-morning share 09:30-11:00; with 45m office travel & 30m O-D travel,
    # only one can fit in that morning slot. P5 must beat P2, while Gamma P4 & Delta P3 still fit!
    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,
        "travelBufferMinutes": 0,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
        "maxVisitsPerDay": 4,
        "useRoadTravelTimes": True,
        "officeToDistributorMinutes": {
            "d-p5-morning": 45,
            "d-p2-morning": 45,
            "d-p4-flex": 15,
            "d-p3-aft": 20,
        },
        "travelTimesMatrix": {
            a["id"]: {b["id"]: (0 if a["id"] == b["id"] else 30) for b in distributors}
            for a in distributors
        },
    }
    res = run_csp_scheduler(distributors, cfg)
    scheduled_ids = {s["distributorId"] for s in res["scheduled"]}
    assert scheduled_ids == {"d-p5-morning", "d-p4-flex", "d-p3-aft"}
    assert [u["distributorId"] for u in res["unscheduled"]] == ["d-p2-morning"]
    _assert_csp_invariants(res, {d["id"]: d for d in distributors}, cfg)


def test_api_schedules_run_enforces_office_travel_and_priority(tmp_path, monkeypatch):
    # Full API integration test via /api/schedules/run with mocked OSRM (45m office travel)
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTESERVICE_API_KEY", raising=False)
    from app.services.routing_service import clear_routing_caches
    clear_routing_caches()

    def fake_osrm_get(url, params=None, headers=None, timeout=None):
        # 1 office + 2 distributors: 45 min (2700s) from office to both stops, 20 min (1200s) between stops
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "code": "Ok",
                "durations": [
                    [0, 2700, 2700],
                    [2700, 0, 1200],
                    [2700, 1200, 0],
                ],
                "distances": [
                    [0, 25000, 25000],
                    [25000, 0, 12000],
                    [25000, 12000, 0],
                ],
            },
        )

    monkeypatch.setattr("app.services.routing_service.requests.get", fake_osrm_get)

    db_file = tmp_path / "csp_regression_api.db"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        }
    )
    with app.test_client() as client:
        assert client.post("/api/db/init").status_code == 200
        off_res = client.post(
            "/api/office",
            json={
                "name": "Test Office",
                "address": "100 Congress Ave, Austin, TX",
                "latitude": 30.2672,
                "longitude": -97.7431,
            },
        )
        assert off_res.status_code == 201
        off_id = off_res.get_json()["data"]["id"]

        d_low_res = client.post(
            "/api/distributors",
            json={
                "name": "Narrow Low P1",
                "contact_person": "Alex Low",
                "phone": "+1-512-555-0101",
                "address": "200 North Lamar Blvd, Austin, TX",
                "latitude": 30.35,
                "longitude": -97.75,
                "priority": 1,
                "visit_duration_minutes": 45,
                "opening_time": "09:00",
                "closing_time": "11:00",
            },
        )
        assert d_low_res.status_code == 201
        d_low = d_low_res.get_json()["data"]["id"]

        d_high_res = client.post(
            "/api/distributors",
            json={
                "name": "Wide High P5",
                "contact_person": "Morgan High",
                "phone": "+1-512-555-0102",
                "address": "300 Parmer Ln, Austin, TX",
                "latitude": 30.40,
                "longitude": -97.70,
                "priority": 5,
                "visit_duration_minutes": 45,
                "opening_time": "09:00",
                "closing_time": "17:00",
            },
        )
        assert d_high_res.status_code == 201
        d_high = d_high_res.get_json()["data"]["id"]

        res = client.post(
            "/api/schedules/run",
            json={
                "officeId": off_id,
                "distributorIds": [d_low, d_high],
                "scheduleDate": "2026-11-22",
                "workStartTime": "09:00",
                "workEndTime": "17:00",
                "slotIncrementMinutes": 15,
                "travelBufferMinutes": 0,
                "lunchBreakEnabled": False,
                "maxVisitsPerDay": 1,
                "useRoadTravelTimes": True,
            },
        )
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert len(data["scheduled"]) == 1
        first = data["scheduled"][0]
        assert first["distributorId"] == d_high
        assert first["startMinutes"] >= time_to_minutes("09:45")
        assert first["travelMinutesFromPrevious"] == 45
        assert len(data["unscheduled"]) == 1
        assert data["unscheduled"][0]["distributorId"] == d_low


def test_csp_off_grid_opening_time_inclusion():
    """Verify distributors with opening times between slot increment grids (e.g. 09:10) can be scheduled."""
    dists = [
        {
            "id": "off_grid_dist",
            "name": "Off Grid Mart",
            "priority": 5,
            "visitDurationMinutes": 30,
            "openingTime": "09:10",
            "closingTime": "10:30",
        }
    ]
    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,  # Grid would be 09:00, 09:15, 09:30...
        "travelBufferMinutes": 0,
        "lunchBreakEnabled": False,
        "maxVisitsPerDay": 5,
        "officeToDistributorMinutes": {"off_grid_dist": 0},
    }
    res = run_csp_scheduler(dists, cfg)
    assert len(res["scheduled"]) == 1
    assert res["scheduled"][0]["distributorId"] == "off_grid_dist"
    # Should be scheduled at 09:10 (exact opening) or 09:15
    assert res["scheduled"][0]["startMinutes"] >= time_to_minutes("09:10")

