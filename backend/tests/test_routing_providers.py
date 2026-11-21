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
from app.services.routing_service import (
    AllRoutingProvidersFailedError,
    build_cost_matrix_with_routing,
    clear_routing_caches,
    compute_route_geometry_with_routing,
)
from app.utils.metrics import clear_matrix_cache


KARACHI_SAMPLE_NODES = [
    {
        "id": "hub",
        "name": "Karachi Central Hub",
        "latitude": 24.8607,
        "longitude": 67.0644,
        "isOffice": True,
    },
    {
        "id": "clifton",
        "name": "Clifton Block 5",
        "latitude": 24.8138,
        "longitude": 67.0299,
        "isOffice": False,
        "visitDurationMinutes": 30,
        "priority": 5,
    },
    {
        "id": "saddar",
        "name": "Saddar Bazaar",
        "latitude": 24.8568,
        "longitude": 67.0185,
        "isOffice": False,
        "visitDurationMinutes": 25,
        "priority": 4,
    },
]


def _setup_clean_env(monkeypatch):
    clear_routing_caches()
    clear_matrix_cache()
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTESERVICE_API_KEY", raising=False)
    monkeypatch.delenv("OSRM_BASE_URL", raising=False)
    monkeypatch.delenv("OSRM_PROFILE", raising=False)


def test_no_google_key_uses_osrm_and_both_objectives(monkeypatch):
    """Case 1, 5, 6: No Google API key -> OSRM returns real road matrix & geometry; both objectives work."""
    _setup_clean_env(monkeypatch)
    requested_urls: list[str] = []

    def fake_osrm_get(url, params=None, headers=None, timeout=None):
        requested_urls.append(url)
        if "/table/v1/driving/" in url:
            # Make tour [0, 2, 1, 0] faster (20 min total) but longer distance (19 km),
            # while tour [0, 1, 2, 0] is shorter distance (12 km) but slower (35 min).
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "code": "Ok",
                    "durations": [
                        [0, 1200, 360],
                        [600, 0, 600],
                        [480, 360, 0],
                    ],
                    "distances": [
                        [0, 3000, 7500],
                        [4500, 0, 4000],
                        [6500, 5000, 0],
                    ],
                },
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 12000.0,
                        "duration": 1200.0,
                        "geometry": "osrm_karachi_polyline_v1",
                    }
                ],
            },
        )

    monkeypatch.setattr("app.services.routing_service.requests.get", fake_osrm_get)

    mat_fast = build_cost_matrix_with_routing(
        KARACHI_SAMPLE_NODES,
        travel_mode="DRIVE",
        optimization_objective="FASTEST_TIME",
    )
    assert any("/table/v1/driving/" in u for u in requested_urls)
    assert mat_fast.provider == "osrm"
    assert mat_fast.providerLabel == "OSRM / OpenStreetMap"
    assert mat_fast.dataSource == "osrm_osm"
    assert mat_fast.isLiveTraffic is False
    assert mat_fast.durationType == "estimated_road_duration"
    assert mat_fast.trafficCalculatedAt is None
    assert mat_fast.roadDistanceAvailable is True

    # FASTEST_TIME: [0, 2, 1, 0] = 6 + 6 + 10 = 22 min (19 km) vs [0, 1, 2, 0] = 20 + 10 + 8 = 38 min (13.5 km)
    ucs_fast = run_ucs(mat_fast, return_to_office=True, optimization_objective="FASTEST_TIME")
    astar_fast = run_astar(mat_fast, return_to_office=True, optimization_objective="FASTEST_TIME")
    ga_fast = run_genetic_algorithm(
        mat_fast,
        return_to_office=True,
        seed=42,
        population_size=40,
        generations=40,
        mutation_rate=0.18,
        optimization_objective="FASTEST_TIME",
    )
    assert ucs_fast["routeOrder"] == [0, 2, 1, 0]
    assert astar_fast["routeOrder"] == [0, 2, 1, 0]
    assert ga_fast["routeOrder"] == [0, 2, 1, 0]

    # SHORTEST_DISTANCE: [0, 1, 2, 0] = 3 + 4 + 6.5 = 13.5 km vs [0, 2, 1, 0] = 7.5 + 5 + 4.5 = 17 km
    mat_short = build_cost_matrix_with_routing(
        KARACHI_SAMPLE_NODES,
        travel_mode="DRIVE",
        optimization_objective="SHORTEST_DISTANCE",
    )
    ucs_short = run_ucs(mat_short, return_to_office=True, optimization_objective="SHORTEST_DISTANCE")
    astar_short = run_astar(mat_short, return_to_office=True, optimization_objective="SHORTEST_DISTANCE")
    ga_short = run_genetic_algorithm(
        mat_short,
        return_to_office=True,
        seed=42,
        population_size=40,
        generations=40,
        mutation_rate=0.18,
        optimization_objective="SHORTEST_DISTANCE",
    )
    assert ucs_short["routeOrder"] == [0, 1, 2, 0]
    assert astar_short["routeOrder"] == [0, 1, 2, 0]
    assert ga_short["routeOrder"] == [0, 1, 2, 0]

    # BFS stays hop-count based
    bfs = run_bfs(mat_fast, return_to_office=True, optimization_objective="FASTEST_TIME")
    assert "does not minimize" in bfs["objectiveDescription"].lower()

    geom = compute_route_geometry_with_routing(KARACHI_SAMPLE_NODES, travel_mode="DRIVE")
    assert geom["provider"] == "osrm"
    assert geom["isLiveTraffic"] is False
    assert geom["encodedPolyline"] == "osrm_karachi_polyline_v1"


def test_google_failure_automatically_falls_back_to_osrm(monkeypatch):
    """Case 2: Google failure -> automatically tries OSRM."""
    _setup_clean_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-google-key-xyz")

    monkeypatch.setattr(
        "app.services.google_maps_service.requests.post",
        lambda *args, **kwargs: SimpleNamespace(status_code=403, json=lambda: {"error": "billing disabled"}),
    )
    monkeypatch.setattr(
        "app.services.routing_service.requests.get",
        lambda url, **kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {
                "code": "Ok",
                "durations": [[0, 600, 480], [600, 0, 300], [480, 300, 0]],
                "distances": [[0, 5000, 4000], [5000, 0, 2500], [4000, 2500, 0]],
            },
        ),
    )

    mat = build_cost_matrix_with_routing(KARACHI_SAMPLE_NODES)
    assert mat.provider == "osrm"
    assert mat.dataSource == "osrm_osm"
    assert mat.isLiveTraffic is False
    assert "secret-google-key-xyz" not in (mat.fallbackReason or "")
    assert mat.providerAttempts[0]["provider"] == "google_maps"
    assert mat.providerAttempts[0]["status"] == "failed"
    assert mat.providerAttempts[1]["provider"] == "osrm"
    assert mat.providerAttempts[1]["status"] == "succeeded"


def test_osrm_failure_falls_back_to_openrouteservice_when_configured(monkeypatch):
    """Case 3: OSRM failure -> tries OpenRouteService if OPENROUTESERVICE_API_KEY is configured."""
    _setup_clean_env(monkeypatch)
    monkeypatch.setenv("OPENROUTESERVICE_API_KEY", "secret-ors-key-123")

    monkeypatch.setattr(
        "app.services.routing_service.requests.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=503, json=lambda: {"code": "Unavailable"}),
    )

    def fake_ors_post(url, json=None, headers=None, timeout=None):
        assert headers["Authorization"] == "secret-ors-key-123"
        if "/v2/matrix/" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "distances": [[0, 8200, 6100], [8300, 0, 4200], [6200, 4300, 0]],
                    "durations": [[0, 720, 540], [740, 0, 360], [550, 380, 0]],
                },
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "routes": [
                    {
                        "geometry": "ors_encoded_polyline_abc",
                        "summary": {"distance": 12400.0, "duration": 1080.0},
                    }
                ]
            },
        )

    monkeypatch.setattr("app.services.routing_service.requests.post", fake_ors_post)

    mat = build_cost_matrix_with_routing(KARACHI_SAMPLE_NODES, travel_mode="DRIVE")
    assert mat.provider == "openrouteservice"
    assert mat.providerLabel == "OpenRouteService"
    assert mat.dataSource == "openrouteservice"
    assert mat.isLiveTraffic is False
    assert mat.distanceKm[0][1] == pytest.approx(8.2, abs=1e-3)
    assert mat.durationMinutes[0][1] == pytest.approx(12.0, abs=1e-2)
    assert "secret-ors-key-123" not in json.dumps(mat.to_dict())

    geom = compute_route_geometry_with_routing(KARACHI_SAMPLE_NODES[:2], travel_mode="DRIVE")
    assert geom["provider"] == "openrouteservice"
    assert geom["encodedPolyline"] == "ors_encoded_polyline_abc"
    assert geom["isLiveTraffic"] is False


def test_all_providers_fail_raises_explicit_error_and_api_returns_503(tmp_path, monkeypatch):
    """Case 4: All real-road providers fail -> explicit error raised & HTTP 503 returned (no simulated fallback)."""
    _setup_clean_env(monkeypatch)
    monkeypatch.setenv("OPENROUTESERVICE_API_KEY", "ors-failing-secret")

    monkeypatch.setattr(
        "app.services.routing_service.requests.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=503, json=lambda: {"code": "Error"}),
    )
    monkeypatch.setattr(
        "app.services.routing_service.requests.post",
        lambda *args, **kwargs: SimpleNamespace(status_code=502, json=lambda: {"error": "bad gateway"}),
    )

    with pytest.raises(AllRoutingProvidersFailedError) as exc_info:
        build_cost_matrix_with_routing(KARACHI_SAMPLE_NODES)
    assert len(exc_info.value.attempts) == 3
    assert "ors-failing-secret" not in str(exc_info.value)

    db_file = tmp_path / "all_fail.db"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
            "OPENROUTESERVICE_API_KEY": "ors-failing-secret",
        }
    )
    with app.test_client() as client:
        assert client.post("/api/db/init").status_code == 200
        assert client.post("/api/demo/load").status_code == 201
        off_id = client.get("/api/office").get_json()["data"]["offices"][0]["id"]
        dists = client.get("/api/distributors?pageSize=5").get_json()["data"]["items"]
        dist_ids = [d["id"] for d in dists[:3]]

        prev_res = client.post(
            "/api/optimize/preview",
            json={"officeId": off_id, "distributorIds": dist_ids, "travelMode": "DRIVE"},
        )
        assert prev_res.status_code == 503
        prev_json = prev_res.get_json()
        assert prev_json["success"] is False
        assert prev_json["error"]["code"] == "ROUTING_PROVIDERS_UNAVAILABLE"
        assert "ors-failing-secret" not in json.dumps(prev_json)

        geom_res = client.post(
            "/api/maps/route-geometry",
            json={
                "waypoints": [
                    {"latitude": 24.8607, "longitude": 67.0644},
                    {"latitude": 24.8138, "longitude": 67.0299},
                ],
                "travelMode": "DRIVE",
            },
        )
        assert geom_res.status_code == 503
        assert geom_res.get_json()["error"]["code"] == "ROUTING_PROVIDERS_UNAVAILABLE"

        sched_res = client.post(
            "/api/schedules/run",
            json={
                "officeId": off_id,
                "distributorIds": dist_ids,
                "scheduleDate": "2026-11-22",
                "workStartTime": "09:00",
                "workEndTime": "17:00",
                "useRoadTravelTimes": True,
            },
        )
        assert sched_res.status_code == 503
        assert sched_res.get_json()["error"]["code"] == "ROUTING_PROVIDERS_UNAVAILABLE"


def test_csp_uses_osrm_road_travel_durations(tmp_path, monkeypatch):
    """Case 6: CSP scheduling uses actual OSRM travel durations."""
    _setup_clean_env(monkeypatch)

    def fake_osrm_get(url, params=None, headers=None, timeout=None):
        # 1 office + 2 distributors (3x3): make dist0->dist1 take 40 min
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "code": "Ok",
                "durations": [
                    [0, 300, 600],
                    [300, 0, 2400],
                    [600, 2400, 0],
                ],
                "distances": [
                    [0, 2000, 4000],
                    [2000, 0, 18000],
                    [4000, 18000, 0],
                ],
            },
        )

    monkeypatch.setattr("app.services.routing_service.requests.get", fake_osrm_get)

    db_file = tmp_path / "csp_osrm.db"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_CONFIGURED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        }
    )
    with app.test_client() as client:
        assert client.post("/api/db/init").status_code == 200
        assert client.post("/api/demo/load").status_code == 201
        off_id = client.get("/api/office").get_json()["data"]["offices"][0]["id"]
        dists = client.get("/api/distributors?pageSize=5").get_json()["data"]["items"][:2]

        res = client.post(
            "/api/schedules/run",
            json={
                "officeId": off_id,
                "distributorIds": [d["id"] for d in dists],
                "scheduleDate": "2026-11-22",
                "workStartTime": "09:00",
                "workEndTime": "17:00",
                "slotIncrementMinutes": 15,
                "travelBufferMinutes": 0,
                "lunchBreakEnabled": False,
                "maxVisitsPerDay": 8,
                "useRoadTravelTimes": True,
            },
        )
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["provider"] == "osrm"
        assert data["dataSource"] == "osrm_osm"
        assert data["isLiveTraffic"] is False
        assert data["usesFixedTravelBuffer"] is False
        assert len(data["scheduled"]) == 2
        assert data["scheduled"][1]["travelMinutesFromPrevious"] == pytest.approx(40.0, abs=1.0)


def test_live_osrm_karachi_real_request(monkeypatch):
    """Case 7: Real live HTTP request to OSRM demo server for Karachi coordinates."""
    _setup_clean_env(monkeypatch)

    mat = build_cost_matrix_with_routing(
        KARACHI_SAMPLE_NODES,
        travel_mode="DRIVE",
        optimization_objective="FASTEST_TIME",
    )
    assert mat.provider == "osrm"
    assert mat.dataSource == "osrm_osm"
    assert mat.isLiveTraffic is False
    assert mat.roadDistanceAvailable is True
    assert mat.distanceKm[0][1] > 4.0
    assert mat.durationMinutes[0][1] > 2.0

    geom = compute_route_geometry_with_routing(
        [KARACHI_SAMPLE_NODES[0], KARACHI_SAMPLE_NODES[1], KARACHI_SAMPLE_NODES[0]],
        travel_mode="DRIVE",
        optimization_objective="FASTEST_TIME",
    )
    assert geom["provider"] == "osrm"
    assert geom["dataSource"] == "osrm_osm"
    assert geom["isLiveTraffic"] is False
    assert isinstance(geom["encodedPolyline"], str) and len(geom["encodedPolyline"]) > 20
    assert geom["distanceKm"] > 8.0
    assert geom["durationMinutes"] > 4.0
