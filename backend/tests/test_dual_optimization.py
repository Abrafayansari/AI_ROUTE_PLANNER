from __future__ import annotations

import json
from types import SimpleNamespace
import pytest

from app import create_app
from app.algorithms import (
    run_astar,
    run_bfs,
    run_csp_scheduler,
    run_genetic_algorithm,
    run_ucs,
)
from app.services.google_maps_service import (
    build_cost_matrix_with_google_or_fallback,
    clear_google_maps_caches,
    compute_google_route_geometry,
)
from app.utils.metrics import CostMatrixResult, clear_matrix_cache


def _make_dual_conflict_nodes():
    # Node 0: Office
    # Node 1: Short distance from 0 (2 km) but congested (40 min from 0->1), fast back to 0 (4 min)
    # Node 2: Longer distance from 0 (6 km) but fast highway (5 min from 0->2), 1->2 is slow vs 2->1 fast
    return [
        {"id": "office", "name": "Karachi Hub", "latitude": 24.8607, "longitude": 67.0644, "isOffice": True},
        {"id": "d1", "name": "Saddar Congested", "latitude": 24.8568, "longitude": 67.0185, "isOffice": False},
        {"id": "d2", "name": "Clifton Bypass", "latitude": 24.8138, "longitude": 67.0299, "isOffice": False},
    ]


def _dual_conflict_matrix(objective: str = "FASTEST_TIME") -> CostMatrixResult:
    # Tour [0, 1, 2, 0]:
    #   Distance: 0->1 (2) + 1->2 (3) + 2->0 (9) = 14 km
    #   Duration: 0->1 (40) + 1->2 (25) + 2->0 (15) = 80 min
    # Tour [0, 2, 1, 0]:
    #   Distance: 0->2 (8) + 2->1 (4) + 1->0 (5) = 17 km  (LONGER distance)
    #   Duration: 0->2 (7) + 2->1 (6) + 1->0 (8) = 21 min  (MUCH FASTER due to less congestion)
    nodes = _make_dual_conflict_nodes()
    dist = [
        [0.0, 2.0, 8.0],
        [5.0, 0.0, 3.0],
        [9.0, 4.0, 0.0],
    ]
    dur = [
        [0.0, 40.0, 7.0],
        [8.0, 0.0, 25.0],
        [15.0, 6.0, 0.0],
    ]
    static_dur = [
        [0.0, 10.0, 7.0],
        [8.0, 0.0, 12.0],
        [12.0, 6.0, 0.0],
    ]
    return CostMatrixResult(
        nodes=nodes,
        straightLineKm=dist,
        distanceKm=dist,
        durationMinutes=dur,
        staticDurationMinutes=static_dur,
        seed=42,
        distanceMultiplier=1.0,
        travelMode="DRIVE",
        speedKmh=35.0,
        cacheHit=False,
        matrixKey=f"mock-{objective}",
        optimizationObjective=objective,  # type: ignore[arg-type]
        dataSource="google_live_traffic" if objective == "FASTEST_TIME" else "google_road_distance",
        trafficCalculatedAt="2026-11-21T10:00:00+00:00",
        fallbackReason=None,
        roadDistanceAvailable=True,
    )


def test_fastest_time_vs_shortest_distance_select_different_tours():
    # Scenarios 1, 2, 3, 4:
    # FASTEST_TIME picks [0, 2, 1, 0] (21 min, 17 km)
    # SHORTEST_DISTANCE picks [0, 1, 2, 0] (14 km, 80 min)
    mat_fast = _dual_conflict_matrix("FASTEST_TIME")
    ucs_fast = run_ucs(mat_fast, return_to_office=True, optimization_objective="FASTEST_TIME")
    astar_fast = run_astar(mat_fast, return_to_office=True, optimization_objective="FASTEST_TIME")
    ga_fast = run_genetic_algorithm(
        mat_fast,
        return_to_office=True,
        seed=42,
        population_size=30,
        generations=40,
        mutation_rate=0.18,
        optimization_objective="FASTEST_TIME",
    )

    assert ucs_fast["routeOrder"] == [0, 2, 1, 0]
    assert astar_fast["routeOrder"] == [0, 2, 1, 0]
    assert ga_fast["routeOrder"] == [0, 2, 1, 0]
    assert ucs_fast["totalCost"] == pytest.approx(21.0, abs=1e-6)
    assert astar_fast["totalCost"] == pytest.approx(ucs_fast["totalCost"], abs=1e-6)
    assert ucs_fast["estimatedDurationMinutes"] == pytest.approx(21.0, abs=1e-6)
    assert ucs_fast["trafficDelayMinutes"] == pytest.approx(0.0, abs=1e-6)

    mat_short = _dual_conflict_matrix("SHORTEST_DISTANCE")
    ucs_short = run_ucs(mat_short, return_to_office=True, optimization_objective="SHORTEST_DISTANCE")
    astar_short = run_astar(mat_short, return_to_office=True, optimization_objective="SHORTEST_DISTANCE")
    ga_short = run_genetic_algorithm(
        mat_short,
        return_to_office=True,
        seed=42,
        population_size=30,
        generations=40,
        mutation_rate=0.18,
        optimization_objective="SHORTEST_DISTANCE",
    )

    assert ucs_short["routeOrder"] == [0, 1, 2, 0]
    assert astar_short["routeOrder"] == [0, 1, 2, 0]
    assert ga_short["routeOrder"] == [0, 1, 2, 0]
    assert ucs_short["totalCost"] == pytest.approx(14.0, abs=1e-6)
    assert astar_short["totalCost"] == pytest.approx(ucs_short["totalCost"], abs=1e-6)
    assert ucs_short["estimatedDistanceKm"] == pytest.approx(14.0, abs=1e-6)

    # BFS remains hop-count based and states clearly it does not minimize time or distance
    bfs = run_bfs(mat_fast, return_to_office=True, optimization_objective="FASTEST_TIME")
    assert bfs["completed"] is True
    assert "does not minimize" in bfs["objectiveDescription"].lower()


def test_asymmetric_traffic_matrix_astar_admissibility_matches_ucs(monkeypatch):
    # Scenario 6: Asymmetric computeRouteMatrix where i->j != j->i across 5 nodes
    clear_google_maps_caches()
    clear_matrix_cache()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-server-key-for-test")

    nodes = [
        {"id": "0", "name": "Hub", "latitude": 24.86, "longitude": 67.06, "isOffice": True},
        {"id": "1", "name": "D1", "latitude": 24.87, "longitude": 67.03, "isOffice": False},
        {"id": "2", "name": "D2", "latitude": 24.90, "longitude": 67.08, "isOffice": False},
        {"id": "3", "name": "D3", "latitude": 24.82, "longitude": 67.04, "isOffice": False},
        {"id": "4", "name": "D4", "latitude": 24.84, "longitude": 67.12, "isOffice": False},
    ]

    # Strongly asymmetric travel times and road distances
    dur_mat = [
        [0, 12, 35, 18, 42],
        [48, 0, 14, 29, 11],
        [15, 50, 0, 13, 38],
        [27, 9, 44, 0, 16],
        [10, 33, 21, 52, 0],
    ]
    static_mat = [
        [max(0, x - 3) for x in row] for row in dur_mat
    ]
    dist_mat = [
        [0.0, 5.2, 8.1, 6.0, 11.4],
        [5.9, 0.0, 4.7, 7.3, 4.0],
        [8.0, 6.8, 0.0, 5.1, 9.2],
        [6.4, 3.8, 7.7, 0.0, 5.5],
        [11.0, 9.5, 8.9, 10.4, 0.0],
    ]

    captured_calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        captured_calls.append({"url": url, "json": json, "headers": headers})
        elements = []
        for i in range(len(nodes)):
            for j in range(len(nodes)):
                elements.append(
                    {
                        "originIndex": i,
                        "destinationIndex": j,
                        "condition": "ROUTE_EXISTS",
                        "distanceMeters": int(dist_mat[i][j] * 1000),
                        "duration": f"{int(dur_mat[i][j] * 60)}s",
                        "staticDuration": f"{int(static_mat[i][j] * 60)}s",
                    }
                )
        return SimpleNamespace(status_code=200, json=lambda: elements)

    monkeypatch.setattr("app.services.google_maps_service.requests.post", fake_post)

    mat = build_cost_matrix_with_google_or_fallback(
        nodes,
        travel_mode="DRIVE",
        optimization_objective="FASTEST_TIME",
    )
    assert len(captured_calls) == 1
    assert captured_calls[0]["headers"]["X-Goog-Maps-Solution-ID"] == "gmp_mcp_codeassist_v1_aistudio"
    assert captured_calls[0]["json"]["routingPreference"] == "TRAFFIC_AWARE"
    assert mat.dataSource == "google_live_traffic"
    assert mat.trafficCalculatedAt is not None
    assert mat.durationMinutes[1][0] != mat.durationMinutes[0][1]

    ucs = run_ucs(mat, return_to_office=True, optimization_objective="FASTEST_TIME")
    astar = run_astar(mat, return_to_office=True, optimization_objective="FASTEST_TIME")
    ga = run_genetic_algorithm(
        mat,
        return_to_office=True,
        seed=42,
        population_size=50,
        generations=80,
        mutation_rate=0.18,
        optimization_objective="FASTEST_TIME",
    )

    assert astar["totalCost"] == pytest.approx(ucs["totalCost"], abs=1e-6)
    assert astar["nodesExpanded"] <= ucs["nodesExpanded"]
    assert ga["completed"] is True
    assert ga["totalCost"] >= ucs["totalCost"] - 1e-6


def test_csp_with_road_travel_times_rejects_infeasible_and_accepts_feasible():
    # Scenario 5: CSP must respect O-D travel times between distributors
    distributors = [
        {
            "id": "d1",
            "name": "Morning Hub",
            "priority": 5,
            "visitDurationMinutes": 45,
            "openingTime": "09:00",
            "closingTime": "10:00",
        },
        {
            "id": "d2",
            "name": "Far Hub",
            "priority": 4,
            "visitDurationMinutes": 45,
            "openingTime": "10:00",
            "closingTime": "11:00",
        },
    ]

    # d1 fits 09:00-09:45; next earliest slot for d2 is 10:15 (45m duration ends 11:00).
    # With 45 min O-D travel from d1 -> d2, earliest feasible start for d2 is 09:45 + 45 = 10:30,
    # ending at 11:15 > closingTime 11:00 => d2 is infeasible!
    res_tight = run_csp_scheduler(
        distributors,
        {
            "workStartTime": "09:00",
            "workEndTime": "17:00",
            "slotIncrementMinutes": 15,
            "travelBufferMinutes": 0,
            "lunchBreakEnabled": False,
            "maxVisitsPerDay": 8,
            "useRoadTravelTimes": True,
            "travelTimesMatrix": {"d1": {"d1": 0, "d2": 45}, "d2": {"d1": 45, "d2": 0}},
            "officeToDistributorMinutes": {"d1": 0, "d2": 10},
        },
    )
    assert res_tight["usesFixedTravelBuffer"] is False
    assert len(res_tight["scheduled"]) == 1
    assert res_tight["unscheduled"][0]["distributorId"] == "d2"

    # Now with 20 min O-D travel d1->d2: 09:45 + 20 = 10:05 => next 15m slot 10:15..11:00 fits!
    res_fits = run_csp_scheduler(
        distributors,
        {
            "workStartTime": "09:00",
            "workEndTime": "17:00",
            "slotIncrementMinutes": 15,
            "travelBufferMinutes": 0,
            "lunchBreakEnabled": False,
            "maxVisitsPerDay": 8,
            "useRoadTravelTimes": True,
            "travelTimesMatrix": {"d1": {"d1": 0, "d2": 20}, "d2": {"d1": 20, "d2": 0}},
            "officeToDistributorMinutes": {"d1": 0, "d2": 10},
        },
    )
    assert len(res_fits["scheduled"]) == 2
    assert res_fits["scheduled"][0]["endMinutes"] + 20 <= res_fits["scheduled"][1]["startMinutes"]


def test_google_fallback_to_osrm_when_key_missing_or_upstream_fails(monkeypatch):
    # Scenario 7: Google missing or failing falls back to OSRM (not silent simulated Haversine)
    clear_google_maps_caches()
    clear_matrix_cache()
    from app.services.routing_service import clear_routing_caches

    clear_routing_caches()
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTESERVICE_API_KEY", raising=False)
    nodes = _make_dual_conflict_nodes()

    def fake_osrm_get(url, params=None, headers=None, timeout=None):
        if "/table/v1/" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "code": "Ok",
                    "durations": [[0, 600, 420], [540, 0, 360], [450, 390, 0]],
                    "distances": [[0, 5200, 6100], [5100, 0, 3400], [6300, 3600, 0]],
                },
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "code": "Ok",
                "routes": [{"distance": 5200, "duration": 600, "geometry": "osrmMockPoly"}],
            },
        )

    monkeypatch.setattr("app.services.routing_service.requests.get", fake_osrm_get)

    mat_missing = build_cost_matrix_with_google_or_fallback(nodes, travel_mode="DRIVE")
    assert mat_missing.provider == "osrm"
    assert mat_missing.dataSource == "osrm_osm"
    assert mat_missing.isLiveTraffic is False
    assert mat_missing.trafficCalculatedAt is None
    assert mat_missing.roadDistanceAvailable is True

    # Now set Google key but simulate upstream Google HTTP 500 failure -> fails over to OSRM
    clear_routing_caches()
    clear_matrix_cache()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key-that-fails")
    monkeypatch.setattr(
        "app.services.google_maps_service.requests.post",
        lambda *args, **kwargs: SimpleNamespace(status_code=500, json=lambda: {}),
    )
    mat_err = build_cost_matrix_with_google_or_fallback(nodes, travel_mode="DRIVE")
    assert mat_err.provider == "osrm"
    assert mat_err.dataSource == "osrm_osm"
    assert mat_err.isLiveTraffic is False
    assert "osrm" in (mat_err.fallbackReason or "").lower()

    # Also test compute_google_route_geometry fallback to OSRM when Google key is missing
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    geom_fb = compute_google_route_geometry(nodes[:2], travel_mode="DRIVE")
    assert geom_fb["encodedPolyline"] == "osrmMockPoly"
    assert geom_fb["provider"] == "osrm"
    assert geom_fb["dataSource"] == "osrm_osm"
    assert geom_fb["isLiveTraffic"] is False


def test_google_route_geometry_shorter_distance_reference_and_attribution(monkeypatch):
    clear_google_maps_caches()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-geom-key")
    captured = []

    def fake_routes_post(url, json=None, headers=None, timeout=None):
        captured.append({"url": url, "json": json, "headers": headers})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "routes": [
                    {
                        "distanceMeters": 8500,
                        "duration": "600s",
                        "staticDuration": "540s",
                        "polyline": {"encodedPolyline": "fast_poly"},
                        "routeLabels": ["DEFAULT_ROUTE"],
                    },
                    {
                        "distanceMeters": 6100,
                        "duration": "780s",
                        "staticDuration": "720s",
                        "polyline": {"encodedPolyline": "short_poly"},
                        "routeLabels": ["SHORTER_DISTANCE"],
                    },
                ]
            },
        )

    monkeypatch.setattr("app.services.google_maps_service.requests.post", fake_routes_post)
    res = compute_google_route_geometry(
        _make_dual_conflict_nodes()[:2],
        travel_mode="DRIVE",
        optimization_objective="SHORTEST_DISTANCE",
    )
    assert len(captured) == 1
    assert captured[0]["json"]["requestedReferenceRoutes"] == ["SHORTER_DISTANCE"]
    assert "routes.routeLabels" in captured[0]["headers"]["X-Goog-FieldMask"]
    assert "routes.routeToken" in captured[0]["headers"]["X-Goog-FieldMask"]
    assert captured[0]["headers"]["X-Goog-Maps-Solution-ID"] == "gmp_mcp_codeassist_v1_aistudio"
    assert res["encodedPolyline"] == "short_poly"
    assert res["distanceKm"] == pytest.approx(6.1, abs=1e-3)
    assert res["dataSource"] == "google_road_distance"


def test_dual_optimization_api_endpoints_and_validation(tmp_path, monkeypatch):
    # Scenario 8: Full API round-trip with SQLite, mocked Google API, and validation checks
    clear_google_maps_caches()
    clear_matrix_cache()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-secret-google-key")

    def fake_post(url, json=None, headers=None, timeout=None):
        if "computeRouteMatrix" in url:
            origins = json["origins"]
            dests = json["destinations"]
            elems = []
            for i in range(len(origins)):
                for j in range(len(dests)):
                    if i == j:
                        elems.append(
                            {
                                "originIndex": i,
                                "destinationIndex": j,
                                "condition": "ROUTE_EXISTS",
                                "distanceMeters": 0,
                                "duration": "0s",
                                "staticDuration": "0s",
                            }
                        )
                    else:
                        # Make 0->1 shorter dist (2km) slow traffic (30m) and 0->2 slightly longer (3km) fast (6m)
                        dist_m = 2000 + ((i + j) % 3) * 1000
                        dur_s = 1800 if (i == 0 and j == 1) else 360 + ((i + j) % 3) * 120
                        elems.append(
                            {
                                "originIndex": i,
                                "destinationIndex": j,
                                "condition": "ROUTE_EXISTS",
                                "distanceMeters": dist_m,
                                "duration": f"{dur_s}s",
                                "staticDuration": f"{max(120, dur_s - 60)}s",
                            }
                        )
            return SimpleNamespace(status_code=200, json=lambda: elems)
        # computeRoutes
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "routes": [
                    {
                        "distanceMeters": 6200,
                        "duration": "900s",
                        "staticDuration": "780s",
                        "polyline": {"encodedPolyline": "mockEncodedPolyline123"},
                        "routeLabels": ["DEFAULT_ROUTE"],
                    }
                ]
            },
        )

    monkeypatch.setattr("app.services.google_maps_service.requests.post", fake_post)

    db_file = tmp_path / "dual_opt.db"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
            "GOOGLE_MAPS_API_KEY": "test-secret-google-key",
        }
    )

    with app.test_client() as client:
        assert client.post("/api/db/init").status_code == 200
        assert client.post("/api/demo/load").status_code == 201

        status_res = client.get("/api/maps/status")
        assert status_res.status_code == 200
        status_json = status_res.get_json()
        assert status_json["data"]["serverConfigured"] is True
        assert "test-secret-google-key" not in json.dumps(status_json)

        off_id = client.get("/api/office").get_json()["data"]["offices"][0]["id"]
        dists = client.get("/api/distributors?pageSize=5").get_json()["data"]["items"]
        dist_ids = [d["id"] for d in dists[:3]]

        # Invalid optimizationObjective -> HTTP 400 VALIDATION_ERROR
        bad_opt = client.post(
            "/api/optimize/preview",
            json={
                "officeId": off_id,
                "distributorIds": dist_ids,
                "optimizationObjective": "CHEAPEST_FUEL",
            },
        )
        assert bad_opt.status_code == 400
        assert bad_opt.get_json()["error"]["code"] == "VALIDATION_ERROR"

        # Default preview -> FASTEST_TIME + google_live_traffic + encodedPolyline
        fast_prev = client.post(
            "/api/optimize/preview",
            json={
                "officeId": off_id,
                "distributorIds": dist_ids,
                "travelMode": "DRIVE",
            },
        )
        assert fast_prev.status_code == 200
        fast_data = fast_prev.get_json()["data"]
        assert fast_data["optimizationObjective"] == "FASTEST_TIME"
        assert fast_data["dataSource"] == "google_live_traffic"
        assert fast_data["trafficCalculatedAt"] is not None
        assert fast_data["encodedPolyline"] == "mockEncodedPolyline123"
        assert "test-secret-google-key" not in json.dumps(fast_data)

        # Save + optimize + switch objective via PUT
        cp = client.post(
            "/api/route-plans",
            json={
                "name": "Dual Objective Test Plan",
                "planDate": "2026-11-22",
                "officeId": off_id,
                "distributorIds": dist_ids,
                "travelMode": "DRIVE",
                "optimizationObjective": "FASTEST_TIME",
            },
        )
        assert cp.status_code == 201
        plan_id = cp.get_json()["data"]["id"]

        op = client.post(
            f"/api/route-plans/{plan_id}/optimize",
            json={"optimizationObjective": "FASTEST_TIME", "travelMode": "DRIVE"},
        )
        assert op.status_code == 200
        assert op.get_json()["data"]["optimizationObjective"] == "FASTEST_TIME"

        # Switch to SHORTEST_DISTANCE
        sw = client.put(
            f"/api/route-plans/{plan_id}",
            json={"optimizationObjective": "SHORTEST_DISTANCE"},
        )
        assert sw.status_code == 200
        assert sw.get_json()["data"]["optimization_objective"] == "SHORTEST_DISTANCE"
        assert sw.get_json()["data"]["data_source"] == "google_road_distance"

        # Route geometry endpoint
        geom_bad = client.post("/api/maps/route-geometry", json={"waypoints": [{"latitude": 24.8, "longitude": 67.0}]})
        assert geom_bad.status_code == 400
        assert geom_bad.get_json()["error"]["code"] == "VALIDATION_ERROR"

        geom_ok = client.post(
            "/api/maps/route-geometry",
            json={
                "waypoints": [
                    {"latitude": 24.8607, "longitude": 67.0644},
                    {"latitude": 24.8138, "longitude": 67.0299},
                ],
                "travelMode": "DRIVE",
                "optimizationObjective": "FASTEST_TIME",
            },
        )
        assert geom_ok.status_code == 200
        assert geom_ok.get_json()["data"]["encodedPolyline"] == "mockEncodedPolyline123"
