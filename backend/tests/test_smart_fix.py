from __future__ import annotations

import json
from datetime import datetime, timezone
import pytest

from app import create_app
from app.extensions import db
from app.models import Distributor, OfficeLocation, RoutePlan, ScheduleEntry
from app.services.scheduling_service import (
    apply_smart_fix_proposal,
    restore_schedule_backup,
    smart_fix_schedule,
)
from app.algorithms.smart_fix import (
    diagnose_schedule,
    repair_schedule_quick_fix,
    repair_schedule_smart_optimize,
)


@pytest.fixture
def app_ctx(tmp_path):
    test_db = tmp_path / "test_smart_fix.db"
    app = create_app({
        "TESTING": True,
        "DATABASE_CONFIGURED": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{test_db}",
    })
    with app.app_context():
        db.create_all()

        office = OfficeLocation(
            id="c0000000-0000-0000-0000-000000000001",
            name="Test Central Office",
            address="Karachi Center",
            latitude=24.8607,
            longitude=67.0011,
            is_default=True,
        )
        db.session.add(office)

        d1 = Distributor(
            id="11111111-1111-1111-1111-111111111111",
            name="Alpha Pharmacy",
            contact_person="Ahmed",
            phone="03001234567",
            address="Clifton Block 2",
            latitude=24.8138,
            longitude=67.0299,
            priority=5,
            visit_duration_minutes=30,
            opening_time="09:00",
            closing_time="17:00",
            is_active=True,
        )
        d2 = Distributor(
            id="22222222-2222-2222-2222-222222222222",
            name="Beta Traders",
            contact_person="Bilal",
            phone="03001234568",
            address="Saddar Market",
            latitude=24.8568,
            longitude=67.0185,
            priority=3,
            visit_duration_minutes=30,
            opening_time="10:00",
            closing_time="18:00",
            is_active=True,
        )
        d3 = Distributor(
            id="33333333-3333-3333-3333-333333333333",
            name="Gamma Mart",
            contact_person="Ghani",
            phone="03001234569",
            address="Gulshan Block 5",
            latitude=24.9200,
            longitude=67.0900,
            priority=1,
            visit_duration_minutes=30,
            opening_time="11:00",
            closing_time="17:00",
            is_active=True,
        )
        db.session.add_all([d1, d2, d3])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


def test_diagnostics_sufficient_travel_buffer_gap(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d1", "name": "Alpha", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "18:00", "priority": 5, "visit_duration_minutes": 30}
    d2 = {"id": "d2", "name": "Beta", "latitude": 24.85, "longitude": 67.01, "opening_time": "09:00", "closing_time": "18:00", "priority": 3, "visit_duration_minutes": 30}

    cfg = {"workStartTime": "09:00", "workEndTime": "17:00", "travelBufferMinutes": 15, "lunchBreakEnabled": False}
    entries = [
        {"distributorId": "d1", "distributorName": "Alpha", "startTime": "09:45", "endTime": "10:15", "visit_duration_minutes": 30},
        {"distributorId": "d2", "distributorName": "Beta", "startTime": "11:00", "endTime": "11:30", "visit_duration_minutes": 30},
    ]

    res = diagnose_schedule(entries, office, [d1, d2], cfg)
    travel_issues = [i for i in res["issues"] if i["type"] == "INSUFFICIENT_TRAVEL_BUFFER"]
    assert len(travel_issues) == 0
    assert res["valid"] is True


def test_diagnostics_insufficient_travel_buffer_gap(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d1", "name": "Alpha", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "18:00", "priority": 5, "visit_duration_minutes": 30}
    d2 = {"id": "d2", "name": "Beta", "latitude": 24.85, "longitude": 67.01, "opening_time": "09:00", "closing_time": "18:00", "priority": 3, "visit_duration_minutes": 30}

    cfg = {"workStartTime": "09:00", "workEndTime": "17:00", "travelBufferMinutes": 20, "lunchBreakEnabled": False}
    # d1 ends at 10:00, d2 starts at 10:05 -> available transition is only 5m, while buffer alone is 20m!
    entries = [
        {"distributorId": "d1", "distributorName": "Alpha", "startTime": "09:30", "endTime": "10:00", "visit_duration_minutes": 30},
        {"distributorId": "d2", "distributorName": "Beta", "startTime": "10:05", "endTime": "10:35", "visit_duration_minutes": 30},
    ]

    res = diagnose_schedule(entries, office, [d1, d2], cfg)
    travel_issues = [i for i in res["issues"] if i["type"] == "INSUFFICIENT_TRAVEL_BUFFER"]
    assert len(travel_issues) >= 1
    # Check that shortfall on transition between d1 and d2 is reported
    d2_issue = next(i for i in travel_issues if i["distributorId"] == "d2")
    assert d2_issue["shortfallMinutes"] >= 15


def test_diagnostics_distributor_closing_time_conflict(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d1", "name": "Early Bird", "latitude": 24.81, "longitude": 67.02, "opening_time": "08:00", "closing_time": "12:00", "priority": 4, "visit_duration_minutes": 30}

    cfg = {"workStartTime": "09:00", "workEndTime": "17:00", "travelBufferMinutes": 10, "lunchBreakEnabled": False}
    entries = [
        {"distributorId": "d1", "distributorName": "Early Bird", "startTime": "12:15", "endTime": "12:45", "visit_duration_minutes": 30},
    ]

    res = diagnose_schedule(entries, office, [d1], cfg)
    closing_issues = [i for i in res["issues"] if i["type"] == "OPERATING_WINDOW_LATE"]
    assert len(closing_issues) == 1
    assert "closes at 12:00" in closing_issues[0]["message"]


def test_diagnostics_lunch_conflict(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d1", "name": "Lunch Clashing", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "18:00", "priority": 3, "visit_duration_minutes": 60}

    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
    }
    entries = [
        {"distributorId": "d1", "distributorName": "Lunch Clashing", "startTime": "12:45", "endTime": "13:45", "visit_duration_minutes": 60},
    ]

    res = diagnose_schedule(entries, office, [d1], cfg)
    lunch_issues = [i for i in res["issues"] if i["type"] == "LUNCH_OVERLAP"]
    assert len(lunch_issues) == 1
    assert "mandatory lunch break" in lunch_issues[0]["message"]


def test_diagnostics_working_hour_violation(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d1", "name": "Overtime", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "20:00", "priority": 2, "visit_duration_minutes": 60}

    cfg = {"workStartTime": "09:00", "workEndTime": "17:00", "travelBufferMinutes": 15, "lunchBreakEnabled": False}
    entries = [
        {"distributorId": "d1", "distributorName": "Overtime", "startTime": "16:30", "endTime": "17:30", "visit_duration_minutes": 60},
    ]

    res = diagnose_schedule(entries, office, [d1], cfg)
    work_issues = [i for i in res["issues"] if i["type"] == "WORK_HOURS_VIOLATION"]
    assert len(work_issues) == 1
    assert "after officer shift end" in work_issues[0]["message"]


def test_diagnostics_missing_coordinates(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d_bad", "name": "Broken GPS", "latitude": None, "longitude": 67.02, "opening_time": "09:00", "closing_time": "18:00", "priority": 3, "visit_duration_minutes": 30}

    cfg = {"workStartTime": "09:00", "workEndTime": "17:00", "travelBufferMinutes": 15, "lunchBreakEnabled": False}
    entries = []

    res = diagnose_schedule(entries, office, [d1], cfg)
    gps_issues = [i for i in res["issues"] if i["type"] == "INVALID_COORDINATES"]
    assert len(gps_issues) == 1


def test_quick_fix_preserves_visit_order(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    d1 = {"id": "d1", "name": "First", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "18:00", "priority": 5, "visit_duration_minutes": 30}
    d2 = {"id": "d2", "name": "Second", "latitude": 24.85, "longitude": 67.01, "opening_time": "09:00", "closing_time": "18:00", "priority": 4, "visit_duration_minutes": 30}
    d3 = {"id": "d3", "name": "Third", "latitude": 24.90, "longitude": 67.05, "opening_time": "09:00", "closing_time": "18:00", "priority": 3, "visit_duration_minutes": 30}

    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
        "maxVisitsPerDay": 8,
    }
    # Deliberately conflicting schedule (d1, d2, d3 overlapping at 09:00)
    entries = [
        {"distributorId": "d1", "distributorName": "First", "startTime": "09:00", "endTime": "09:30", "visit_duration_minutes": 30},
        {"distributorId": "d2", "distributorName": "Second", "startTime": "09:00", "endTime": "09:30", "visit_duration_minutes": 30},
        {"distributorId": "d3", "distributorName": "Third", "startTime": "09:00", "endTime": "09:30", "visit_duration_minutes": 30},
    ]

    repaired = repair_schedule_quick_fix(entries, office, [d1, d2, d3], cfg)
    assert repaired["feasible"] is True
    assert len(repaired["scheduled"]) == 3
    # Order must be preserved
    assert [s["distributorId"] for s in repaired["scheduled"]] == ["d1", "d2", "d3"]
    # Check that visits are non-overlapping with required buffer
    for i in range(len(repaired["scheduled"]) - 1):
        curr_end = repaired["scheduled"][i]["endMinutes"]
        next_start = repaired["scheduled"][i + 1]["startMinutes"]
        assert next_start >= curr_end + 15


def test_quick_fix_unscheduled_when_cannot_fit(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    # d2 closes very early at 09:30
    d1 = {"id": "d1", "name": "Slow Stop", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "18:00", "priority": 5, "visit_duration_minutes": 60}
    d2 = {"id": "d2", "name": "Early Closing", "latitude": 24.85, "longitude": 67.01, "opening_time": "09:00", "closing_time": "09:45", "priority": 3, "visit_duration_minutes": 30}

    cfg = {"workStartTime": "09:00", "workEndTime": "17:00", "travelBufferMinutes": 15, "lunchBreakEnabled": False, "maxVisitsPerDay": 8}
    entries = [
        {"distributorId": "d1", "distributorName": "Slow Stop", "startTime": "09:00", "endTime": "10:00", "visit_duration_minutes": 60},
        {"distributorId": "d2", "distributorName": "Early Closing", "startTime": "10:00", "endTime": "10:30", "visit_duration_minutes": 30},
    ]

    repaired = repair_schedule_quick_fix(entries, office, [d1, d2], cfg)
    assert len(repaired["scheduled"]) == 1
    assert repaired["scheduled"][0]["distributorId"] == "d1"
    assert len(repaired["unscheduled"]) == 1
    assert repaired["unscheduled"][0]["distributorId"] == "d2"
    assert "closing time" in repaired["unscheduled"][0]["reason"]


def test_smart_optimize_improves_or_satisfies_hard_constraints(app_ctx):
    office = {"id": "c0000000-0000-0000-0000-000000000001", "name": "Office", "latitude": 24.86, "longitude": 67.0}
    # d1 has priority 5, d2 has priority 1
    d1 = {"id": "d1", "name": "High Priority", "latitude": 24.81, "longitude": 67.02, "opening_time": "09:00", "closing_time": "17:00", "priority": 5, "visit_duration_minutes": 30}
    d2 = {"id": "d2", "name": "Low Priority", "latitude": 24.85, "longitude": 67.01, "opening_time": "09:00", "closing_time": "17:00", "priority": 1, "visit_duration_minutes": 30}

    cfg = {
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "slotIncrementMinutes": 15,
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
        "lunchStartTime": "12:30",
        "lunchDurationMinutes": 60,
        "maxVisitsPerDay": 8,
    }

    opt_res = repair_schedule_smart_optimize(office, [d1, d2], cfg)
    assert opt_res["feasible"] is True
    assert len(opt_res["scheduled"]) == 2
    assert "objectiveWeights" in opt_res
    assert opt_res["objectiveWeights"]["wPriority"] == 100.0


def test_smart_fix_end_to_end_preview_and_apply(app_ctx):
    plan = RoutePlan(
        name="Smart Fix Test Plan",
        plan_date=datetime.now(timezone.utc).date(),
        office_id="c0000000-0000-0000-0000-000000000001",
    )
    db.session.add(plan)
    db.session.commit()
    pid = str(plan.id)

    # Add initial conflicting entry
    entry = ScheduleEntry(
        route_plan_id=pid,
        distributor_id="11111111-1111-1111-1111-111111111111",
        distributor_name="Alpha Pharmacy",
        scheduled_start=datetime.fromisoformat("2026-11-21T09:00:00+00:00"),
        scheduled_end=datetime.fromisoformat("2026-11-21T09:30:00+00:00"),
        visit_duration_minutes=30,
        priority=5,
    )
    db.session.add(entry)
    db.session.commit()

    # Step 1: Preview Smart Fix
    preview_cfg = {
        "mode": "QUICK_FIX",
        "routePlanId": pid,
        "officeId": "c0000000-0000-0000-0000-000000000001",
        "scheduleDate": "2026-11-21",
        "workStartTime": "09:00",
        "workEndTime": "17:00",
        "travelBufferMinutes": 15,
        "lunchBreakEnabled": True,
    }
    preview_res = smart_fix_schedule(preview_cfg)
    assert preview_res["diagnostics"] is not None
    assert "comparison" in preview_res
    assert preview_res["activeProposal"]["feasible"] is True

    # Confirm original schedule remains untouched in DB before apply!
    db_entries_before = db.session.query(ScheduleEntry).filter_by(route_plan_id=pid).all()
    assert len(db_entries_before) == 1
    assert db_entries_before[0].scheduled_start.strftime("%H:%M") == "09:00"

    # Step 2: Apply Smart Fix proposal
    apply_cfg = {
        "routePlanId": pid,
        "officeId": "c0000000-0000-0000-0000-000000000001",
        "scheduleDate": "2026-11-21",
        "mode": "QUICK_FIX",
        "scheduled": preview_res["activeProposal"]["scheduled"],
    }
    apply_res = apply_smart_fix_proposal(apply_cfg)
    assert apply_res["success"] is True

    # Verify DB updated
    db_entries_after = db.session.query(ScheduleEntry).filter_by(route_plan_id=pid).all()
    assert len(db_entries_after) >= 1
    notes = json.loads(db_entries_after[0].constraint_notes)
    assert notes.get("appliedFromSmartFixMode") == "QUICK_FIX"
    assert "backupHistory" in notes

    # Step 3: Restore previous schedule backup
    restore_res = restore_schedule_backup(pid)
    assert restore_res["success"] is True
    assert restore_res["restoredCount"] == 1
    restored_entries = db.session.query(ScheduleEntry).filter_by(route_plan_id=pid).all()
    assert len(restored_entries) == 1
    assert "Restored from pre-Smart Fix backup" in restored_entries[0].constraint_notes
