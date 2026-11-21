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
                "address": "123 Main St",
                "latitude": 95.0,  # out of bounds
                "longitude": -97.0,
                "priority": 3,
                "visit_duration_minutes": 30,
                "opening_time": "17:00",
                "closing_time": "09:00",
            },
        )
        assert res3.status_code == 400
        assert res3.get_json()["error"]["code"] == "VALIDATION_ERROR"
