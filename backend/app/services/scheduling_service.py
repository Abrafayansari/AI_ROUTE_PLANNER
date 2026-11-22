from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.algorithms.bayesian_network import get_bayesian_network
from app.algorithms.csp import run_csp_scheduler
from app.algorithms.smart_fix import (
    diagnose_schedule,
    generate_schedule_suggestions,
    repair_schedule_quick_fix,
    repair_schedule_smart_optimize,
)
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
        notes_payload = {
            "summary": csp_result['constraintsSummary'],
            "bufferMinutes": entry['bufferMinutes'],
            "delayRisk": entry.get('delayRisk', 'Low'),
            "backupSnapshot": {
                "distributorId": entry["distributorId"],
                "startTime": entry["startTime"],
                "endTime": entry["endTime"],
                "visitDurationMinutes": entry["durationMinutes"],
                "priority": entry["priority"],
            },
        }
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
                constraint_notes=json.dumps(notes_payload),
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


def smart_fix_schedule(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Intelligent Schedule Repair Service:
    Executes diagnostics, runs requested mode (QUICK_FIX, SMART_OPTIMIZE, or SUGGESTIONS_ONLY),
    and formats an Old vs. Proposed comparison without modifying database records.
    """
    mode = cfg.get("mode", "QUICK_FIX").upper()
    office = _resolve_office(cfg.get("officeId"))

    dist_ids = cfg.get("distributorIds") or []
    if dist_ids:
        dists = db.session.query(Distributor).filter(Distributor.id.in_(dist_ids)).all()
    else:
        dists = db.session.query(Distributor).filter(Distributor.is_active == True).all()

    dist_dicts = [d.to_dict() for d in dists]
    dist_map = {str(d["id"]): d for d in dist_dicts}

    # Fetch current schedule entries (if routePlanId provided or latest)
    route_plan_id = cfg.get("routePlanId")
    current_entries: list[dict[str, Any]] = []
    if route_plan_id:
        entries = (
            db.session.query(ScheduleEntry)
            .filter_by(route_plan_id=route_plan_id)
            .order_by(ScheduleEntry.scheduled_start.asc())
            .all()
        )
        current_entries = [e.to_dict() for e in entries]
    if not current_entries:
        latest = get_latest_schedule()
        if latest and latest.get("entries"):
            current_entries = latest["entries"]
            if not route_plan_id:
                route_plan_id = latest.get("routePlanId")

    # If still no entries, use distributors in default order
    if not current_entries:
        current_entries = [
            {
                "distributor_id": str(d["id"]),
                "distributor_name": d["name"],
                "priority": d["priority"],
                "visit_duration_minutes": d["visit_duration_minutes"],
                "start_time": "09:00",
                "end_time": "09:30",
            }
            for d in dist_dicts[:8]
        ]

    # Build road matrix if road times enabled
    use_road_times = bool(cfg.get("useRoadTravelTimes", True))
    travel_mode = cfg.get("travelMode", "DRIVE")
    opt_obj = cfg.get("optimizationObjective", OBJECTIVE_FASTEST_TIME)

    road_matrix: CostMatrixResult | None = None
    provider_name = "simulated_fallback"
    data_source = "simulated_fallback"

    if use_road_times and dist_dicts:
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
                "id": str(d["id"]),
                "name": d["name"],
                "latitude": float(d["latitude"]),
                "longitude": float(d["longitude"]),
                "isOffice": False,
            }
            for d in dist_dicts
        ]
        try:
            road_matrix = build_cost_matrix_with_routing(
                nodes,
                seed=42,
                travel_mode=travel_mode,
                optimization_objective=opt_obj,
            )
            provider_name = road_matrix.provider
            data_source = road_matrix.dataSource
        except Exception:
            road_matrix = None

    # Step 1: Run Schedule Diagnostics
    diagnostics = diagnose_schedule(
        entries=current_entries,
        office=office.to_dict(),
        distributors=dist_dicts,
        config=cfg,
        road_matrix=road_matrix,
    )

    # Step 2: Run Repair Modes
    quick_fix_res = repair_schedule_quick_fix(
        current_entries=current_entries,
        office=office.to_dict(),
        distributors=dist_dicts,
        config=cfg,
        road_matrix=road_matrix,
    )

    smart_opt_res = repair_schedule_smart_optimize(
        office=office.to_dict(),
        distributors=dist_dicts,
        config=cfg,
        road_matrix=road_matrix,
    )

    suggestions_res = generate_schedule_suggestions(
        diagnostics=diagnostics,
        quick_fix=quick_fix_res,
        smart_opt=smart_opt_res,
    )

    # Step 3: Select target proposal based on requested mode
    if mode == "SMART_OPTIMIZE":
        active_proposal = smart_opt_res
    elif mode == "SUGGESTIONS_ONLY":
        active_proposal = {
            "mode": "SUGGESTIONS_ONLY",
            "feasible": True,
            "solverStatus": "ADVISORY_SUGGESTIONS",
            "executionTimeMs": 0.0,
            "scheduled": current_entries,
            "unscheduled": [],
        }
    else:  # QUICK_FIX
        active_proposal = quick_fix_res

    # Step 4: Construct Old vs. Proposed Comparison
    orig_by_id = {
        str(e.get("distributor_id") or e.get("distributorId")): e
        for e in current_entries
    }
    prop_by_id = {
        str(s.get("distributorId") or s.get("distributor_id")): s
        for s in active_proposal.get("scheduled", [])
    }

    comparison_items: list[dict[str, Any]] = []
    all_dids = list(dict.fromkeys(list(orig_by_id.keys()) + list(prop_by_id.keys())))

    for did in all_dids:
        orig = orig_by_id.get(did)
        prop = prop_by_id.get(did)
        d_name = (
            prop.get("distributorName")
            if prop
            else orig.get("distributor_name") or orig.get("distributorName") or "Unknown"
        )
        d_meta = dist_map.get(did)

        if orig and prop:
            orig_start = orig.get("start_time") or orig.get("startTime", "09:00")
            prop_start = prop.get("startTime") or prop.get("start_time", "09:00")
            status = "MOVED" if orig_start != prop_start else "UNCHANGED"
        elif not orig and prop:
            status = "ADDED"
            orig_start = None
            prop_start = prop.get("startTime") or prop.get("start_time", "09:00")
        else:
            status = "REMOVED"
            orig_start = orig.get("start_time") or orig.get("startTime", "09:00")
            prop_start = None

        comparison_items.append({
            "distributorId": did,
            "distributorName": d_name,
            "status": status,
            "originalStartTime": orig_start,
            "proposedStartTime": prop_start,
            "originalEndTime": orig.get("end_time") or orig.get("endTime") if orig else None,
            "proposedEndTime": prop.get("endTime") or prop.get("end_time") if prop else None,
            "visitDurationMinutes": (
                prop.get("durationMinutes")
                if prop
                else orig.get("visit_duration_minutes") or 30
            ),
            "priority": d_meta["priority"] if d_meta else 3,
            "openingTime": d_meta["opening_time"] if d_meta else "08:00",
            "closingTime": d_meta["closing_time"] if d_meta else "18:00",
            "travelMinutes": prop.get("travelMinutesFromPrevious") if prop else None,
            "bufferMinutes": prop.get("bufferMinutes") if prop else None,
            "delayRisk": prop.get("delayRisk") if prop else orig.get("delayRisk"),
        })

    # Resolved vs Remaining issues
    diagnostics_on_proposal = diagnose_schedule(
        entries=active_proposal.get("scheduled", []),
        office=office.to_dict(),
        distributors=dist_dicts,
        config=cfg,
        road_matrix=road_matrix,
    )

    resolved_count = max(0, diagnostics["issueCount"] - diagnostics_on_proposal["issueCount"])

    return {
        "mode": mode,
        "routePlanId": route_plan_id,
        "officeId": str(office.id),
        "officeName": office.name,
        "provider": provider_name,
        "dataSource": data_source,
        "diagnostics": diagnostics,
        "activeProposal": active_proposal,
        "quickFix": quick_fix_res,
        "smartOptimize": smart_opt_res,
        "suggestions": suggestions_res,
        "comparison": {
            "items": comparison_items,
            "movedCount": len([c for c in comparison_items if c["status"] == "MOVED"]),
            "unchangedCount": len([c for c in comparison_items if c["status"] == "UNCHANGED"]),
            "addedCount": len([c for c in comparison_items if c["status"] == "ADDED"]),
            "removedCount": len([c for c in comparison_items if c["status"] == "REMOVED"]),
            "resolvedIssuesCount": resolved_count,
            "remainingIssuesCount": diagnostics_on_proposal["issueCount"],
            "remainingIssues": diagnostics_on_proposal["issues"],
        },
    }


def apply_smart_fix_proposal(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Applies the confirmed Smart Fix proposal to the database.
    Archives previous schedule records into a backup snapshot for rollback support.
    """
    route_plan_id = cfg.get("routePlanId")
    if not route_plan_id:
        latest = get_latest_schedule()
        if latest and latest.get("routePlanId"):
            route_plan_id = latest["routePlanId"]
        else:
            raise ValueError("No active routePlanId found to apply Smart Fix.")

    proposed_scheduled = cfg.get("scheduled") or []
    if not proposed_scheduled:
        raise ValueError("Cannot apply an empty proposed schedule.")

    office = _resolve_office(cfg.get("officeId"))
    schedule_date = cfg.get("scheduleDate") or "2026-11-21"

    # Capture backup snapshot of existing schedule before overwriting
    existing_entries = (
        db.session.query(ScheduleEntry)
        .filter_by(route_plan_id=route_plan_id)
        .order_by(ScheduleEntry.scheduled_start.asc())
        .all()
    )
    backup_snapshot = [
        {
            "distributor_id": str(e.distributor_id) if e.distributor_id else None,
            "distributor_name": e.distributor_name,
            "scheduled_start": e.scheduled_start.isoformat() if e.scheduled_start else None,
            "scheduled_end": e.scheduled_end.isoformat() if e.scheduled_end else None,
            "visit_duration_minutes": e.visit_duration_minutes,
            "priority": e.priority,
            "travel_from_previous_minutes": e.travel_from_previous_minutes,
            "distance_from_previous_km": e.distance_from_previous_km,
            "data_source": e.data_source,
        }
        for e in existing_entries
    ]

    # Delete existing entries and insert proposed entries
    db.session.query(ScheduleEntry).filter_by(route_plan_id=route_plan_id).delete()

    data_source = cfg.get("dataSource", "osrm_osm")
    for entry in proposed_scheduled:
        start_str = entry.get("startTime") or entry.get("start_time")
        end_str = entry.get("endTime") or entry.get("end_time")
        dur = int(entry.get("durationMinutes") or entry.get("visit_duration_minutes") or 30)

        notes_payload = {
            "appliedFromSmartFixMode": cfg.get("mode", "QUICK_FIX"),
            "bufferMinutes": entry.get("bufferMinutes", 15),
            "delayRisk": entry.get("delayRisk", "Low"),
            "backupHistory": backup_snapshot,
        }

        db.session.add(
            ScheduleEntry(
                route_plan_id=route_plan_id,
                distributor_id=entry.get("distributorId") or entry.get("distributor_id"),
                distributor_name=entry.get("distributorName") or entry.get("distributor_name"),
                scheduled_start=_to_utc_datetime(schedule_date, start_str),
                scheduled_end=_to_utc_datetime(schedule_date, end_str),
                visit_duration_minutes=dur,
                priority=int(entry.get("priority", 3)),
                travel_from_previous_minutes=entry.get("travelMinutesFromPrevious") or entry.get("travel_from_previous_minutes"),
                distance_from_previous_km=entry.get("distanceKm") or entry.get("distance_from_previous_km"),
                data_source=data_source,
                is_feasible=True,
                constraint_notes=json.dumps(notes_payload),
            )
        )

    db.session.commit()

    return {
        "success": True,
        "message": f"Successfully applied {len(proposed_scheduled)} repaired visits to schedule.",
        "routePlanId": route_plan_id,
        "appliedCount": len(proposed_scheduled),
        "backupCount": len(backup_snapshot),
    }


def restore_schedule_backup(route_plan_id: str) -> dict[str, Any]:
    """
    Restores the previous schedule snapshot from backup history stored in constraint_notes.
    """
    first_entry = (
        db.session.query(ScheduleEntry)
        .filter_by(route_plan_id=route_plan_id)
        .first()
    )
    if not first_entry or not first_entry.constraint_notes:
        raise LookupError("No backup snapshot found for this route plan.")

    try:
        parsed_notes = json.loads(first_entry.constraint_notes)
        backup_list = parsed_notes.get("backupHistory")
        if not backup_list:
            raise LookupError("No previous schedule backup available in record notes.")
    except Exception as exc:
        raise LookupError(f"Could not parse backup snapshot: {exc}")

    # Remove current entries and restore from backup
    db.session.query(ScheduleEntry).filter_by(route_plan_id=route_plan_id).delete()

    for item in backup_list:
        db.session.add(
            ScheduleEntry(
                route_plan_id=route_plan_id,
                distributor_id=item["distributor_id"],
                distributor_name=item["distributor_name"],
                scheduled_start=datetime.fromisoformat(item["scheduled_start"]).astimezone(timezone.utc),
                scheduled_end=datetime.fromisoformat(item["scheduled_end"]).astimezone(timezone.utc),
                visit_duration_minutes=item["visit_duration_minutes"],
                priority=item["priority"],
                travel_from_previous_minutes=item.get("travel_from_previous_minutes"),
                distance_from_previous_km=item.get("distance_from_previous_km"),
                data_source=item.get("data_source", "osrm_osm"),
                is_feasible=True,
                constraint_notes="Restored from pre-Smart Fix backup snapshot.",
            )
        )

    db.session.commit()

    return {
        "success": True,
        "message": f"Restored {len(backup_list)} visits from pre-repair snapshot.",
        "routePlanId": route_plan_id,
        "restoredCount": len(backup_list),
    }
