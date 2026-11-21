from __future__ import annotations

from datetime import datetime, timezone

from app.algorithms.bayesian_network import get_bayesian_network
from app.algorithms.csp import run_csp_scheduler
from app.extensions import db
from app.models import Distributor, OfficeLocation, RoutePlan, ScheduleEntry
from app.models.route_stop import format_clock_from_iso
from app.services.clustering_service import resolve_workspace_route_plan_id
from app.services.google_maps_service import OBJECTIVE_FASTEST_TIME
from app.services.routing_service import build_cost_matrix_with_routing
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

        dist_km: float | None = (
            round(float(e.distance_from_previous_km), 2)
            if e.distance_from_previous_km is not None
            else None
        )
        if dist_km is None and dist is not None and prev_lat is not None and prev_lng is not None:
            dist_km = round(
                haversine_km(prev_lat, prev_lng, float(dist.latitude), float(dist.longitude)),
                2,
            )
        if dist is not None:
            prev_lat = float(dist.latitude)
            prev_lng = float(dist.longitude)

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
                "travel_from_previous_minutes": e.travel_from_previous_minutes,
                "distanceKm": dist_km,
                "dataSource": e.data_source or "simulated_fallback",
                "delayRisk": pred["predictedRisk"],
                "delayProbabilities": pred["probabilities"],
                "recommendedBufferMinutes": pred["recommendedBufferMinutes"],
                "delayAdvisory": pred.get("recommendation"),
            }
        )

    sched_ds = entries[0].data_source or "osrm_osm"
    provider_map = {
        "google_live_traffic": ("google_maps", "Google Maps", "Live traffic travel duration (Google Routes API)"),
        "google_road_distance": ("google_maps", "Google Maps", "Static road travel duration (Google Routes API)"),
        "osrm_osm": ("osrm", "OSRM / OpenStreetMap", "Estimated road travel duration (OSRM / OpenStreetMap — no live traffic)"),
        "openrouteservice": ("openrouteservice", "OpenRouteService", "Estimated road travel duration (OpenRouteService — no live traffic)"),
    }
    p_id, p_label, dur_label = provider_map.get(
        sched_ds,
        ("simulated_fallback", "Fixed Buffer", "Fixed buffer schedule"),
    )

    return {
        "routePlanId": route_plan_id,
        "officeId": str(office.id) if office else None,
        "officeName": office.name if office else None,
        "scheduleDate": schedule_date,
        "provider": p_id,
        "providerLabel": p_label,
        "dataSource": sched_ds,
        "isLiveTraffic": sched_ds == "google_live_traffic",
        "durationType": "live_traffic" if sched_ds == "google_live_traffic" else "estimated_road_duration",
        "durationLabel": dur_label,
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
    ordered_dists = [dist_map[did] for did in dist_ids]

    use_road_times = bool(cfg.get("useRoadTravelTimes", True))
    travel_mode = cfg.get("travelMode", "DRIVE")
    optimization_objective = cfg.get("optimizationObjective", OBJECTIVE_FASTEST_TIME)

    csp_cfg = dict(cfg)
    provider = "simulated_fallback"
    provider_label = "Fixed Travel Buffer"
    data_source = "simulated_fallback"
    is_live_traffic = False
    duration_type = "simulated"
    duration_label = "Fixed buffer (O–D road travel times disabled)"
    traffic_calculated_at = None
    calculated_at = None
    fallback_reason = None
    provider_attempts: list[dict] = []

    if use_road_times:
        nodes = [
            {
                "id": str(office.id),
                "name": office.name,
                "latitude": float(office.latitude),
                "longitude": float(office.longitude),
                "isOffice": True,
            }
        ] + [
            {
                "id": str(d.id),
                "name": d.name,
                "latitude": float(d.latitude),
                "longitude": float(d.longitude),
                "isOffice": False,
            }
            for d in ordered_dists
        ]
        matrix = build_cost_matrix_with_routing(
            nodes,
            seed=42,
            distance_multiplier=1.0,
            travel_mode=travel_mode,  # type: ignore[arg-type]
            optimization_objective=optimization_objective,  # type: ignore[arg-type]
        )
        provider = matrix.provider
        provider_label = matrix.providerLabel
        data_source = matrix.dataSource
        is_live_traffic = matrix.isLiveTraffic
        duration_type = matrix.durationType
        duration_label = matrix.durationLabel
        traffic_calculated_at = matrix.trafficCalculatedAt
        calculated_at = matrix.calculatedAt
        fallback_reason = matrix.fallbackReason
        provider_attempts = matrix.providerAttempts

        travel_times_matrix: dict[str, dict[str, float]] = {}
        distance_km_matrix: dict[str, dict[str, float]] = {}
        office_to_dist_min: dict[str, float] = {}
        office_to_dist_km: dict[str, float] = {}

        for j in range(1, len(nodes)):
            dj = nodes[j]["id"]
            office_to_dist_min[dj] = matrix.durationMinutes[0][j]
            office_to_dist_km[dj] = matrix.distanceKm[0][j]

        for i in range(1, len(nodes)):
            di = nodes[i]["id"]
            travel_times_matrix[di] = {}
            distance_km_matrix[di] = {}
            for j in range(1, len(nodes)):
                dj = nodes[j]["id"]
                travel_times_matrix[di][dj] = matrix.durationMinutes[i][j]
                distance_km_matrix[di][dj] = matrix.distanceKm[i][j]

        csp_cfg["travelTimesMatrix"] = travel_times_matrix
        csp_cfg["distanceKmMatrix"] = distance_km_matrix
        csp_cfg["officeToDistributorMinutes"] = office_to_dist_min
        csp_cfg["officeToDistributorKm"] = office_to_dist_km
        csp_cfg["dataSource"] = data_source

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
            for d in ordered_dists
        ],
        csp_cfg,
    )

    bn = get_bayesian_network()
    high_risk_entries: list[str] = []
    advisories: list[str] = []

    prev_lat = float(office.latitude)
    prev_lng = float(office.longitude)
    for entry in csp_result["scheduled"]:
        curr_d = dist_map.get(entry["distributorId"])
        dist_km = entry.get("distanceKm")
        if dist_km is None:
            if curr_d is not None:
                dist_km = round(
                    haversine_km(prev_lat, prev_lng, float(curr_d.latitude), float(curr_d.longitude)),
                    2,
                )
            else:
                dist_km = 0.0
        if curr_d is not None:
            prev_lat = float(curr_d.latitude)
            prev_lng = float(curr_d.longitude)

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
                travel_from_previous_minutes=entry.get("travelMinutesFromPrevious"),
                distance_from_previous_km=entry.get("distanceKm"),
                data_source=data_source,
                is_feasible=True,
                constraint_notes=(
                    f"{csp_result['constraintsSummary']} (+{entry['bufferMinutes']}m travel) "
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
        "provider": provider,
        "providerLabel": provider_label,
        "dataSource": data_source,
        "isLiveTraffic": is_live_traffic,
        "durationType": duration_type,
        "durationLabel": duration_label,
        "trafficCalculatedAt": traffic_calculated_at,
        "calculatedAt": calculated_at,
        "fallbackReason": fallback_reason,
        "providerAttempts": provider_attempts,
        **csp_result,
    }
