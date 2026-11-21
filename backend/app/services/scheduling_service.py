from __future__ import annotations

from datetime import datetime, timezone

from app.algorithms.bayesian_network import get_bayesian_network
from app.algorithms.csp import run_csp_scheduler
from app.extensions import db
from app.models import Distributor, OfficeLocation, RoutePlan, ScheduleEntry
from app.models.route_stop import format_clock_from_iso
from app.services.clustering_service import resolve_workspace_route_plan_id
from app.utils.metrics import haversine_km


def _to_utc_datetime(date_str: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{date_str}T{hhmm}:00+00:00").astimezone(timezone.utc)


def _resolve_office(office_id: str | None = None) -> OfficeLocation:
    if office_id:
        office = db.session.get(OfficeLocation, office_id)
        if office is None:
            raise ValueError("NO_OFFICE_LOCATION")
        return office
    office = (
        db.session.query(OfficeLocation)
        .order_by(OfficeLocation.is_default.desc(), OfficeLocation.created_at.asc())
        .first()
    )
    if office is None:
        raise ValueError("NO_OFFICE_LOCATION")
    return office


def get_latest_schedule() -> dict | None:
    latest = (
        db.session.query(ScheduleEntry)
        .filter(
            ScheduleEntry.route_plan_id.isnot(None),
            ScheduleEntry.scheduled_start.isnot(None),
        )
        .order_by(ScheduleEntry.created_at.desc())
        .first()
    )
    if latest is None:
        return None

    route_plan_id = str(latest.route_plan_id)
    plan = db.session.get(RoutePlan, route_plan_id)
    office = db.session.get(OfficeLocation, str(plan.office_id)) if plan else None

    entries = (
        db.session.query(ScheduleEntry)
        .filter(
            ScheduleEntry.route_plan_id == route_plan_id,
            ScheduleEntry.scheduled_start.isnot(None),
        )
        .order_by(ScheduleEntry.scheduled_start.asc())
        .all()
    )
    if not entries:
        return None

    first_start = entries[0].scheduled_start
    schedule_date = (
        first_start.date().isoformat()
        if isinstance(first_start, datetime)
        else str(first_start)[:10]
    )

    bn = get_bayesian_network()
    prev_lat = float(office.latitude) if office is not None else None
    prev_lng = float(office.longitude) if office is not None else None

    formatted = []
    high_risk_entries: list[str] = []
    advisories: list[str] = []

    for e in entries:
        dist = e.distributor
        dist_dur = int(e.visit_duration_minutes or 30)
        start_time_str = format_clock_from_iso(e.scheduled_start) or "09:00"

        dist_km: float | None = None
        if dist is not None and prev_lat is not None and prev_lng is not None:
            dist_km = round(
                haversine_km(prev_lat, prev_lng, float(dist.latitude), float(dist.longitude)),
                2,
            )
            prev_lat = float(dist.latitude)
            prev_lng = float(dist.longitude)
        elif dist is not None:
            prev_lat = float(dist.latitude)
            prev_lng = float(dist.longitude)

        # Calculate delay risk prediction (marginalizes Distance cleanly if coords unavailable)
        pred = bn.predict_visit(
            distributor_id=str(e.distributor_id) if e.distributor_id else None,
            distributor_name=e.distributor_name,
            distance_km=dist_km,
            visit_duration_minutes=dist_dur,
            time_slot_raw=start_time_str,
            priority_raw=int(e.priority or 3),
            route_plan_id=route_plan_id,
            allow_partial=dist_km is None,
        )

        if pred["predictedRisk"] == "High" or pred["probabilities"]["High"] >= 0.45:
            high_risk_entries.append(e.distributor_name)
            if pred.get("recommendation"):
                advisories.append(f"{e.distributor_name}: {pred['recommendation']}")

        formatted.append(
            {
                "id": str(e.id),
                "distributor_id": str(e.distributor_id) if e.distributor_id else str(e.id),
                "distributor_name": e.distributor_name,
                "priority": int(e.priority or 3),
                "start_time": start_time_str,
                "end_time": format_clock_from_iso(e.scheduled_end) or "09:30",
                "visit_duration_minutes": dist_dur,
                "opening_time": dist.opening_time if dist else "08:00",
                "closing_time": dist.closing_time if dist else "18:00",
                "schedule_date": schedule_date,
                "constraint_notes": e.constraint_notes or "",
                "distanceKm": dist_km,
                "delayRisk": pred["predictedRisk"],
                "delayProbabilities": pred["probabilities"],
                "recommendedBufferMinutes": pred["recommendedBufferMinutes"],
                "delayAdvisory": pred.get("recommendation"),
            }
        )

    return {
        "routePlanId": route_plan_id,
        "officeId": str(office.id) if office else None,
        "officeName": office.name if office else None,
        "scheduleDate": schedule_date,
        "entries": formatted,
        "bayesianAdvisory": {
            "evaluatedCount": len(formatted),
            "highRiskCount": len(high_risk_entries),
            "highRiskDistributors": high_risk_entries,
            "recommendedTravelBuffer": 25 if high_risk_entries else 15,
            "hasHighRisk": len(high_risk_entries) > 0,
            "recommendationText": (
                f"Bayesian Network identified {len(high_risk_entries)} high-delay risk visit(s) ({', '.join(high_risk_entries)}). "
                f"Advisory: Consider increasing travel buffer or shifting afternoon appointments earlier."
                if high_risk_entries
                else "All scheduled visits exhibit Low to Moderate predicted delay risk."
            ),
            "advisoryDetails": advisories,
        },
    }


def run_and_save_schedule(cfg: dict) -> dict:
    dist_ids: list[str] = cfg["distributorIds"]
    dists = db.session.query(Distributor).filter(Distributor.id.in_(dist_ids)).all()
    if len(dists) != len(dist_ids):
        raise LookupError("One or more selected distributors do not exist.")

    office = _resolve_office(cfg.get("officeId"))
    dist_map = {str(d.id): d for d in dists}

    csp_result = run_csp_scheduler(
        [
            {
                "id": str(d.id),
                "name": d.name,
                "priority": int(d.priority),
                "visitDurationMinutes": int(d.visit_duration_minutes),
                "openingTime": d.opening_time,
                "closingTime": d.closing_time,
            }
            for d in dists
        ],
        cfg,
    )

    bn = get_bayesian_network()
    high_risk_entries: list[str] = []
    advisories: list[str] = []

    # Run Bayesian inference on each scheduled stop starting from base office
    prev_lat = float(office.latitude)
    prev_lng = float(office.longitude)
    for entry in csp_result["scheduled"]:
        curr_d = dist_map.get(entry["distributorId"])
        if curr_d is not None:
            dist_km = round(
                haversine_km(prev_lat, prev_lng, float(curr_d.latitude), float(curr_d.longitude)),
                2,
            )
            prev_lat = float(curr_d.latitude)
            prev_lng = float(curr_d.longitude)
        else:
            dist_km = 0.0

        pred = bn.predict_visit(
            distributor_id=entry["distributorId"],
            distributor_name=entry["distributorName"],
            distance_km=dist_km,
            visit_duration_minutes=entry["durationMinutes"],
            time_slot_raw=entry["startTime"],
            priority_raw=entry["priority"],
        )

        entry["delayRisk"] = pred["predictedRisk"]
        entry["delayProbabilities"] = pred["probabilities"]
        entry["recommendedBufferMinutes"] = pred["recommendedBufferMinutes"]
        entry["delayAdvisory"] = pred.get("recommendation")
        entry["distanceKm"] = dist_km

        if pred["predictedRisk"] == "High" or pred["probabilities"]["High"] >= 0.45:
            high_risk_entries.append(entry["distributorName"])
            if pred.get("recommendation"):
                advisories.append(f"{entry['distributorName']}: {pred['recommendation']}")

    recommended_travel_buffer = (
        cfg.get("travelBufferMinutes", 15) + 10
        if high_risk_entries
        else cfg.get("travelBufferMinutes", 15)
    )

    csp_result["bayesianAdvisory"] = {
        "evaluatedCount": len(csp_result["scheduled"]),
        "highRiskCount": len(high_risk_entries),
        "highRiskDistributors": high_risk_entries,
        "recommendedTravelBuffer": recommended_travel_buffer,
        "hasHighRisk": len(high_risk_entries) > 0,
        "recommendationText": (
            f"Bayesian Network identified {len(high_risk_entries)} high-delay risk visit(s) ({', '.join(high_risk_entries)}). "
            f"Advisory: Consider increasing travel buffer to {recommended_travel_buffer} min or re-evaluating afternoon appointments."
            if high_risk_entries
            else "All scheduled visits exhibit Low to Moderate predicted delay risk."
        ),
        "advisoryDetails": advisories,
    }

    schedule_date = cfg["scheduleDate"]
    target_plan_id = resolve_workspace_route_plan_id(
        cfg.get("routePlanId"),
        f"CSP Schedule — {schedule_date}",
        schedule_date,
        office_id=str(office.id),
    )

    db.session.query(ScheduleEntry).filter_by(route_plan_id=target_plan_id).delete()
    for entry in csp_result["scheduled"]:
        db.session.add(
            ScheduleEntry(
                route_plan_id=target_plan_id,
                distributor_id=entry["distributorId"],
                distributor_name=entry["distributorName"],
                scheduled_start=_to_utc_datetime(schedule_date, entry["startTime"]),
                scheduled_end=_to_utc_datetime(schedule_date, entry["endTime"]),
                visit_duration_minutes=entry["durationMinutes"],
                priority=entry["priority"],
                is_feasible=True,
                constraint_notes=(
                    f"{csp_result['constraintsSummary']} (+{entry['bufferMinutes']}m buffer) "
                    f"[Bayes Risk: {entry.get('delayRisk', 'Low')}]"
                ),
            )
        )
    db.session.commit()

    return {
        "routePlanId": target_plan_id,
        "officeId": str(office.id),
        "officeName": office.name,
        "scheduleDate": schedule_date,
        **csp_result,
    }
