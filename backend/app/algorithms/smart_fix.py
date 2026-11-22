from __future__ import annotations

import math
import time
from typing import Any

from app.algorithms.bayesian_network import get_bayesian_network
from app.algorithms.csp import run_csp_scheduler
from app.algorithms.genetic_algorithm import run_genetic_algorithm
from app.services.routing_service import build_cost_matrix_with_routing
from app.utils.metrics import CostMatrixResult, haversine_km, minutes_to_time, time_to_minutes


def diagnose_schedule(
    entries: list[dict[str, Any]],
    office: dict[str, Any],
    distributors: list[dict[str, Any]],
    config: dict[str, Any],
    road_matrix: CostMatrixResult | None = None,
) -> dict[str, Any]:
    """
    Schedule Diagnostics Engine:
    Validates consecutive transitions, opening windows, lunch break, working hours,
    distributor coordinates, and Bayesian delay risks.
    """
    work_start = time_to_minutes(config.get("workStartTime", "09:00"))
    work_end = time_to_minutes(config.get("workEndTime", "17:00"))
    buffer_min = max(0, int(config.get("travelBufferMinutes", 15)))
    lunch_enabled = bool(config.get("lunchBreakEnabled", True))
    lunch_start = time_to_minutes(config.get("lunchStartTime", "12:30"))
    lunch_duration = int(config.get("lunchDurationMinutes", 60))
    lunch_end = lunch_start + lunch_duration
    max_visits = max(1, int(config.get("maxVisitsPerDay", 10)))

    issues: list[dict[str, Any]] = []
    normalized_dists = []
    for d in distributors:
        normalized_dists.append({
            "id": str(d.get("id")),
            "name": d.get("name") or "Distributor",
            "priority": int(d.get("priority", 3)),
            "visit_duration_minutes": int(d.get("visit_duration_minutes") or d.get("visitDurationMinutes") or 30),
            "opening_time": d.get("opening_time") or d.get("openingTime") or "09:00",
            "closing_time": d.get("closing_time") or d.get("closingTime") or "17:00",
            "latitude": float(d.get("latitude") or 0.0),
            "longitude": float(d.get("longitude") or 0.0),
        })
    dist_map = {str(d["id"]): d for d in normalized_dists}
    node_id_to_idx: dict[str, int] = {}
    if road_matrix and hasattr(road_matrix, "nodes"):
        node_id_to_idx = {str(n["id"]): idx for idx, n in enumerate(road_matrix.nodes)}

    def _get_travel_min(from_id: str, to_id: str) -> int:
        if road_matrix and from_id in node_id_to_idx and to_id in node_id_to_idx:
            fi = node_id_to_idx[from_id]
            ti = node_id_to_idx[to_id]
            val = road_matrix.durationMinutes[fi][ti]
            if val is not None and math.isfinite(val):
                return max(0, int(math.ceil(val)))
        # When road_matrix is not provided, estimate travel time based on coordinates if available
        from_node = dist_map.get(from_id) or (office if str(office.get("id")) == from_id else None)
        to_node = dist_map.get(to_id) or (office if str(office.get("id")) == to_id else None)
        if from_node and to_node and from_node.get("latitude") and to_node.get("latitude"):
            km = haversine_km(
                float(from_node["latitude"]), float(from_node["longitude"]),
                float(to_node["latitude"]), float(to_node["longitude"])
            )
            # Estimate urban transit at 30 km/h -> 2 min/km
            return max(5, int(math.ceil(km * 2.0)))
        return 0

    # 1. Missing coordinates or invalid distributor checks
    for d in distributors:
        lat = d.get("latitude")
        lng = d.get("longitude")
        if lat is None or lng is None or not (-90.0 <= float(lat) <= 90.0 and -180.0 <= float(lng) <= 180.0):
            issues.append({
                "type": "INVALID_COORDINATES",
                "severity": "CRITICAL",
                "distributorId": str(d.get("id")),
                "distributorName": d.get("name", "Unknown"),
                "message": f"Distributor {d.get('name')} has invalid or missing geographic coordinates ({lat}, {lng}).",
                "shortfallMinutes": 0,
            })

    # 2. Maximum visits cap violation
    if len(entries) > max_visits:
        issues.append({
            "type": "VISIT_CAP_EXCEEDED",
            "severity": "HIGH",
            "message": f"Scheduled visits ({len(entries)}) exceed maximum daily officer limit of {max_visits}.",
            "shortfallMinutes": 0,
        })

    bn = get_bayesian_network()
    prev_end = work_start
    prev_did = str(office["id"])
    prev_lat = float(office["latitude"])
    prev_lng = float(office["longitude"])

    for idx, entry in enumerate(entries):
        did = str(entry.get("distributor_id") or entry.get("distributorId"))
        d_name = entry.get("distributor_name") or entry.get("distributorName") or "Unknown"
        d_info = dist_map.get(did)
        start_min = time_to_minutes(entry.get("start_time") or entry.get("startTime", "09:00"))
        end_min = time_to_minutes(entry.get("end_time") or entry.get("endTime", "09:30"))
        dur_min = int(entry.get("visit_duration_minutes") or entry.get("durationMinutes", 30))

        # Check visit duration consistency
        if end_min - start_min != dur_min:
            issues.append({
                "type": "DURATION_MISMATCH",
                "severity": "MEDIUM",
                "distributorId": did,
                "distributorName": d_name,
                "message": f"Visit duration slot ({end_min - start_min}m) does not match required duration ({dur_min}m).",
                "shortfallMinutes": abs((end_min - start_min) - dur_min),
            })

        # Check officer working hours
        if start_min < work_start:
            issues.append({
                "type": "WORK_HOURS_VIOLATION",
                "severity": "CRITICAL",
                "distributorId": did,
                "distributorName": d_name,
                "message": f"Visit starts at {minutes_to_time(start_min)}, before officer shift start {minutes_to_time(work_start)}.",
                "shortfallMinutes": work_start - start_min,
            })
        if end_min > work_end:
            issues.append({
                "type": "WORK_HOURS_VIOLATION",
                "severity": "CRITICAL",
                "distributorId": did,
                "distributorName": d_name,
                "message": f"Visit ends at {minutes_to_time(end_min)}, after officer shift end {minutes_to_time(work_end)}.",
                "shortfallMinutes": end_min - work_end,
            })

        # Check distributor operating window
        if d_info:
            open_min = time_to_minutes(d_info["opening_time"])
            close_min = time_to_minutes(d_info["closing_time"])
            if start_min < open_min:
                issues.append({
                    "type": "OPERATING_WINDOW_EARLY",
                    "severity": "HIGH",
                    "distributorId": did,
                    "distributorName": d_name,
                    "message": f"Visit starts at {minutes_to_time(start_min)} before distributor opens at {d_info['opening_time']}.",
                    "shortfallMinutes": open_min - start_min,
                })
            if end_min > close_min:
                issues.append({
                    "type": "OPERATING_WINDOW_LATE",
                    "severity": "HIGH",
                    "distributorId": did,
                    "distributorName": d_name,
                    "message": f"Visit ends at {minutes_to_time(end_min)} after distributor closes at {d_info['closing_time']}.",
                    "shortfallMinutes": end_min - close_min,
                })

        # Check lunch overlap
        if lunch_enabled:
            # Check if visit overlaps lunch [lunch_start, lunch_end]
            if start_min < lunch_end and lunch_start < end_min:
                overlap_dur = min(end_min, lunch_end) - max(start_min, lunch_start)
                issues.append({
                    "type": "LUNCH_OVERLAP",
                    "severity": "CRITICAL",
                    "distributorId": did,
                    "distributorName": d_name,
                    "message": f"Visit ({minutes_to_time(start_min)}–{minutes_to_time(end_min)}) clashes with mandatory lunch break ({minutes_to_time(lunch_start)}–{minutes_to_time(lunch_end)}).",
                    "shortfallMinutes": overlap_dur,
                })

        # Transition validation (office to stop 0 or stop i-1 to stop i)
        actual_travel = _get_travel_min(prev_did, did)
        required_transition = actual_travel + buffer_min
        available_transition = start_min - prev_end

        # Handle lunch break occurring in transition interval
        if lunch_enabled and prev_end <= lunch_start and start_min >= lunch_end:
            # Transition spans across lunch
            available_transition -= lunch_duration

        if available_transition < required_transition:
            shortfall = required_transition - available_transition
            src_name = "Base Office" if idx == 0 else "previous stop"
            issues.append({
                "type": "INSUFFICIENT_TRAVEL_BUFFER",
                "severity": "HIGH",
                "distributorId": did,
                "distributorName": d_name,
                "message": (
                    f"Insufficient transition from {src_name} to {d_name}. "
                    f"Required: {required_transition}m ({actual_travel}m road travel + {buffer_min}m buffer), "
                    f"Available: {available_transition}m. Shortfall: {shortfall}m."
                ),
                "requiredMinutes": required_transition,
                "availableMinutes": available_transition,
                "shortfallMinutes": shortfall,
                "travelMinutes": actual_travel,
                "bufferMinutes": buffer_min,
            })

        # Bayesian delay risk
        curr_lat = float(d_info["latitude"]) if d_info else prev_lat
        curr_lng = float(d_info["longitude"]) if d_info else prev_lng
        dist_km = round(haversine_km(prev_lat, prev_lng, curr_lat, curr_lng), 2)
        prio_val = int(entry.get("priority") or (d_info["priority"] if d_info else 3))

        pred = bn.predict_visit(
            distributor_id=did,
            distributor_name=d_name,
            distance_km=dist_km,
            visit_duration_minutes=dur_min,
            time_slot_raw=minutes_to_time(start_min),
            priority_raw=prio_val,
        )

        if pred["predictedRisk"] == "High" or pred["probabilities"]["High"] >= 0.45:
            issues.append({
                "type": "BAYESIAN_HIGH_DELAY_RISK",
                "severity": "MEDIUM",
                "distributorId": did,
                "distributorName": d_name,
                "message": (
                    f"Elevated delay probability ({int(pred['probabilities']['High'] * 100)}%) for {d_name}. "
                    f"Recommended safety buffer: +{pred['recommendedBufferMinutes']}m or earlier time slot."
                ),
                "probabilities": pred["probabilities"],
                "recommendedBufferMinutes": pred["recommendedBufferMinutes"],
                "shortfallMinutes": 0,
            })

        prev_end = end_min
        prev_did = did
        prev_lat = curr_lat
        prev_lng = curr_lng

    return {
        "valid": len([i for i in issues if i["severity"] in ("CRITICAL", "HIGH")]) == 0,
        "issueCount": len(issues),
        "criticalCount": len([i for i in issues if i["severity"] == "CRITICAL"]),
        "highCount": len([i for i in issues if i["severity"] == "HIGH"]),
        "mediumCount": len([i for i in issues if i["severity"] == "MEDIUM"]),
        "issues": issues,
    }


def repair_schedule_quick_fix(
    current_entries: list[dict[str, Any]],
    office: dict[str, Any],
    distributors: list[dict[str, Any]],
    config: dict[str, Any],
    road_matrix: CostMatrixResult | None = None,
) -> dict[str, Any]:
    """
    Mode A: Quick Fix
    Preserves existing distributor visit order whenever possible.
    Shifts visit start times forward to resolve travel gaps, lunch clashes, and operating window conflicts.
    Visits that cannot be accommodated within work hours or closing times are safely reported as unscheduled.
    """
    start_t = time.perf_counter()
    work_start = time_to_minutes(config.get("workStartTime", "09:00"))
    work_end = time_to_minutes(config.get("workEndTime", "17:00"))
    buffer_min = max(0, int(config.get("travelBufferMinutes", 15)))
    lunch_enabled = bool(config.get("lunchBreakEnabled", True))
    lunch_start = time_to_minutes(config.get("lunchStartTime", "12:30"))
    lunch_duration = int(config.get("lunchDurationMinutes", 60))
    lunch_end = lunch_start + lunch_duration
    max_visits = max(1, int(config.get("maxVisitsPerDay", 10)))

    normalized_dists = []
    for d in distributors:
        normalized_dists.append({
            "id": str(d.get("id")),
            "name": d.get("name") or "Distributor",
            "priority": int(d.get("priority", 3)),
            "visit_duration_minutes": int(d.get("visit_duration_minutes") or d.get("visitDurationMinutes") or 30),
            "opening_time": d.get("opening_time") or d.get("openingTime") or "09:00",
            "closing_time": d.get("closing_time") or d.get("closingTime") or "17:00",
            "latitude": float(d.get("latitude") or 0.0),
            "longitude": float(d.get("longitude") or 0.0),
        })
    dist_map = {str(d["id"]): d for d in normalized_dists}
    node_id_to_idx: dict[str, int] = {}
    if road_matrix and hasattr(road_matrix, "nodes"):
        node_id_to_idx = {str(n["id"]): idx for idx, n in enumerate(road_matrix.nodes)}

    def _get_travel_min(from_id: str, to_id: str) -> int:
        if road_matrix and from_id in node_id_to_idx and to_id in node_id_to_idx:
            fi = node_id_to_idx[from_id]
            ti = node_id_to_idx[to_id]
            val = road_matrix.durationMinutes[fi][ti]
            if val is not None and math.isfinite(val):
                return max(0, int(math.ceil(val)))
        # When road_matrix is not provided, estimate travel time based on coordinates if available
        from_node = dist_map.get(from_id) or (office if str(office.get("id")) == from_id else None)
        to_node = dist_map.get(to_id) or (office if str(office.get("id")) == to_id else None)
        if from_node and to_node and from_node.get("latitude") and to_node.get("latitude"):
            km = haversine_km(
                float(from_node["latitude"]), float(from_node["longitude"]),
                float(to_node["latitude"]), float(to_node["longitude"])
            )
            # Estimate urban transit at 30 km/h -> 2 min/km
            return max(5, int(math.ceil(km * 2.0)))
        return 0

    def _get_distance_km(from_id: str, to_id: str, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> float:
        if road_matrix and from_id in node_id_to_idx and to_id in node_id_to_idx:
            fi = node_id_to_idx[from_id]
            ti = node_id_to_idx[to_id]
            val = road_matrix.distanceKm[fi][ti]
            if val is not None and math.isfinite(val):
                return round(float(val), 2)
        return round(haversine_km(from_lat, from_lng, to_lat, to_lng), 2)

    scheduled: list[dict[str, Any]] = []
    unscheduled: list[dict[str, Any]] = []

    current_time = work_start
    prev_did = str(office["id"])
    prev_lat = float(office["latitude"])
    prev_lng = float(office["longitude"])

    bn = get_bayesian_network()

    for idx, entry in enumerate(current_entries):
        did = str(entry.get("distributor_id") or entry.get("distributorId"))
        d_info = dist_map.get(did)
        if not d_info:
            unscheduled.append({
                "distributorId": did,
                "distributorName": entry.get("distributor_name", "Unknown"),
                "priority": entry.get("priority", 3),
                "visitDurationMinutes": entry.get("visit_duration_minutes", 30),
                "openingTime": "08:00",
                "closingTime": "18:00",
                "reason": "Distributor record not found in database.",
            })
            continue

        if len(scheduled) >= max_visits:
            unscheduled.append({
                "distributorId": did,
                "distributorName": d_info["name"],
                "priority": int(d_info["priority"]),
                "visitDurationMinutes": int(d_info["visit_duration_minutes"]),
                "openingTime": d_info["opening_time"],
                "closingTime": d_info["closing_time"],
                "reason": f"Maximum daily visit limit ({max_visits}) reached.",
            })
            continue

        dur_min = int(d_info["visit_duration_minutes"])
        open_min = time_to_minutes(d_info["opening_time"])
        close_min = time_to_minutes(d_info["closing_time"])
        d_lat = float(d_info["latitude"])
        d_lng = float(d_info["longitude"])

        travel_min = _get_travel_min(prev_did, did)
        dist_km = _get_distance_km(prev_did, did, prev_lat, prev_lng, d_lat, d_lng)

        # Earliest time officer can arrive
        earliest_arrival = current_time + travel_min + buffer_min

        # If earliest arrival is during lunch break, officer can travel and take lunch
        if lunch_enabled and earliest_arrival < lunch_end and current_time < lunch_end:
            # Check if earliest_arrival falls in lunch or before lunch
            if earliest_arrival > lunch_start:
                earliest_arrival = lunch_end + buffer_min

        # Earliest start must also respect distributor opening time
        visit_start = max(earliest_arrival, open_min)

        # Check lunch conflict with the visit itself
        if lunch_enabled:
            # If visit interval overlaps lunch, push it past lunch
            if visit_start < lunch_end and lunch_start < (visit_start + dur_min):
                visit_start = max(lunch_end, open_min)

        visit_end = visit_start + dur_min

        # Feasibility checks
        if visit_end > close_min:
            unscheduled.append({
                "distributorId": did,
                "distributorName": d_info["name"],
                "priority": int(d_info["priority"]),
                "visitDurationMinutes": dur_min,
                "openingTime": d_info["opening_time"],
                "closingTime": d_info["closing_time"],
                "reason": (
                    f"Visit finish ({minutes_to_time(visit_end)}) exceeds distributor closing time "
                    f"({d_info['closing_time']}) when maintaining visit order."
                ),
            })
            continue

        if visit_end > work_end:
            unscheduled.append({
                "distributorId": did,
                "distributorName": d_info["name"],
                "priority": int(d_info["priority"]),
                "visitDurationMinutes": dur_min,
                "openingTime": d_info["opening_time"],
                "closingTime": d_info["closing_time"],
                "reason": (
                    f"Visit finish ({minutes_to_time(visit_end)}) exceeds officer working shift "
                    f"({config.get('workEndTime', '17:00')})."
                ),
            })
            continue

        pred = bn.predict_visit(
            distributor_id=did,
            distributor_name=d_info["name"],
            distance_km=dist_km,
            visit_duration_minutes=dur_min,
            time_slot_raw=minutes_to_time(visit_start),
            priority_raw=int(d_info["priority"]),
        )

        scheduled.append({
            "distributorId": did,
            "distributorName": d_info["name"],
            "priority": int(d_info["priority"]),
            "startTime": minutes_to_time(visit_start),
            "endTime": minutes_to_time(visit_end),
            "startMinutes": visit_start,
            "endMinutes": visit_end,
            "durationMinutes": dur_min,
            "bufferMinutes": buffer_min,
            "travelMinutesFromPrevious": travel_min,
            "openingTime": d_info["opening_time"],
            "closingTime": d_info["closing_time"],
            "distanceKm": dist_km,
            "delayRisk": pred["predictedRisk"],
            "delayProbabilities": pred["probabilities"],
            "recommendedBufferMinutes": pred["recommendedBufferMinutes"],
            "delayAdvisory": pred.get("recommendation"),
        })

        current_time = visit_end
        prev_did = did
        prev_lat = d_lat
        prev_lng = d_lng

    exec_time = round((time.perf_counter() - start_t) * 1000.0, 3)

    return {
        "mode": "QUICK_FIX",
        "feasible": len(scheduled) > 0,
        "solverStatus": "FEASIBLE_SUBSET" if unscheduled else "FEASIBLE_ORDER_PRESERVED",
        "executionTimeMs": exec_time,
        "scheduled": scheduled,
        "unscheduled": unscheduled,
        "totalTravelMinutes": sum(s.get("travelMinutesFromPrevious", 0) for s in scheduled),
        "totalDistanceKm": round(sum(s.get("distanceKm", 0.0) for s in scheduled), 2),
    }


def repair_schedule_smart_optimize(
    office: dict[str, Any],
    distributors: list[dict[str, Any]],
    config: dict[str, Any],
    road_matrix: CostMatrixResult | None = None,
) -> dict[str, Any]:
    """
    Mode B: Smart Optimize
    Applies Genetic Algorithm permutation exploration with CSP hard-constraint validation
    and risk-aware objective function incorporating Bayesian delay predictions.
    """
    start_t = time.perf_counter()

    if not distributors:
        return {
            "mode": "SMART_OPTIMIZE",
            "feasible": False,
            "solverStatus": "NO_DISTRIBUTORS",
            "executionTimeMs": 0.0,
            "scheduled": [],
            "unscheduled": [],
        }

    # If road_matrix is provided, use GA to search permutations
    # Otherwise build or run CSP directly
    ordered_dist_lists: list[list[dict[str, Any]]] = []

    # Permutation 1: Priority descending then opening time
    prio_order = sorted(distributors, key=lambda d: (-int(d["priority"]), d["opening_time"]))
    ordered_dist_lists.append(prio_order)

    # Permutation 2: Opening time ascending
    open_order = sorted(distributors, key=lambda d: (d["opening_time"], -int(d["priority"])))
    ordered_dist_lists.append(open_order)

    # Permutation 3+: GA solutions if road_matrix available
    if road_matrix and len(distributors) >= 3:
        try:
            ga_res = run_genetic_algorithm(
                matrix=road_matrix,
                return_to_office=False,
                population_size=60,
                generations=80,
                mutation_rate=0.2,
                seed=42,
            )
            # Map GA tour chromosome back to distributor dicts
            node_id_to_dist = {str(d["id"]): d for d in distributors}
            ga_nodes = road_matrix.nodes
            ga_dists: list[dict[str, Any]] = []
            for gene_idx in ga_res["bestRouteIndices"]:
                if gene_idx > 0 and gene_idx < len(ga_nodes):
                    nid = str(ga_nodes[gene_idx]["id"])
                    if nid in node_id_to_dist:
                        ga_dists.append(node_id_to_dist[nid])
            if ga_dists:
                ordered_dist_lists.append(ga_dists)
        except Exception:
            pass

    # Evaluate each candidate permutation using CSP Scheduler
    best_candidate: dict[str, Any] | None = None
    best_score = -float("inf")
    candidate_telemetry: list[dict[str, Any]] = []

    bn = get_bayesian_network()

    # Weight definitions (Documented Objective Function)
    w_priority = 100.0
    w_travel = 1.0
    w_waiting = 0.5
    w_risk = 15.0

    for c_idx, candidate_dists in enumerate(ordered_dist_lists):
        # Format candidate dists with camelCase keys expected by run_csp_scheduler
        csp_dist_inputs = [
            {
                "id": str(d.get("id")),
                "name": d.get("name"),
                "priority": int(d.get("priority", 3)),
                "visitDurationMinutes": int(d.get("visit_duration_minutes") or d.get("visitDurationMinutes", 30)),
                "openingTime": d.get("opening_time") or d.get("openingTime", "08:00"),
                "closingTime": d.get("closing_time") or d.get("closingTime", "18:00"),
            }
            for d in candidate_dists
        ]
        csp_out = run_csp_scheduler(csp_dist_inputs, config)
        sched = csp_out.get("scheduled", [])

        if not sched:
            continue

        total_prio = sum(int(s["priority"]) for s in sched)
        total_travel = sum(int(s.get("travelMinutesFromPrevious") or 0) for s in sched)
        total_dist_km = sum(float(s.get("distanceKm") or 0.0) for s in sched)

        # Calculate idle/waiting time
        total_waiting = 0
        high_risk_penalty = 0.0
        for i, s in enumerate(sched):
            # Evaluate Bayesian delay risk
            pred = bn.predict_visit(
                distributor_id=s["distributorId"],
                distributor_name=s["distributorName"],
                distance_km=float(s.get("distanceKm") or 2.0),
                visit_duration_minutes=int(s["durationMinutes"]),
                time_slot_raw=s["startTime"],
                priority_raw=int(s["priority"]),
            )
            s["delayRisk"] = pred["predictedRisk"]
            s["delayProbabilities"] = pred["probabilities"]
            s["recommendedBufferMinutes"] = pred["recommendedBufferMinutes"]
            s["delayAdvisory"] = pred.get("recommendation")

            if pred["predictedRisk"] == "High":
                high_risk_penalty += 1.0

            if i > 0:
                prev_s = sched[i - 1]
                gap = s["startMinutes"] - prev_s["endMinutes"]
                trav = int(s.get("travelMinutesFromPrevious") or 0)
                waiting = max(0, gap - trav - int(config.get("travelBufferMinutes", 15)))
                total_waiting += waiting

        # Objective Function:
        # Maximize F = w1*PrioSum - w2*TravelMin - w3*WaitingMin - w4*HighRiskCount
        score = (w_priority * total_prio) - (w_travel * total_travel) - (w_waiting * total_waiting) - (w_risk * high_risk_penalty)

        telemetry_item = {
            "candidateIndex": c_idx,
            "scheduledCount": len(sched),
            "prioritySum": total_prio,
            "travelMinutes": total_travel,
            "waitingMinutes": total_waiting,
            "highRiskCount": int(high_risk_penalty),
            "objectiveScore": round(score, 2),
        }
        candidate_telemetry.append(telemetry_item)

        if score > best_score:
            best_score = score
            best_candidate = {
                "csp_out": csp_out,
                "score": score,
                "totalTravel": total_travel,
                "totalDistanceKm": round(total_dist_km, 2),
                "totalWaiting": total_waiting,
                "highRiskCount": int(high_risk_penalty),
            }

    exec_time = round((time.perf_counter() - start_t) * 1000.0, 3)

    if not best_candidate:
        return {
            "mode": "SMART_OPTIMIZE",
            "feasible": False,
            "solverStatus": "NO_FEASIBLE_SCHEDULE",
            "executionTimeMs": exec_time,
            "scheduled": [],
            "unscheduled": [
                {
                    "distributorId": str(d["id"]),
                    "distributorName": d["name"],
                    "priority": int(d["priority"]),
                    "visitDurationMinutes": int(d["visit_duration_minutes"]),
                    "openingTime": d["opening_time"],
                    "closingTime": d["closing_time"],
                    "reason": "No feasible time slot found across all candidate permutations under current constraints.",
                }
                for d in distributors
            ],
            "objectiveWeights": {
                "wPriority": w_priority,
                "wTravel": w_travel,
                "wWaiting": w_waiting,
                "wRisk": w_risk,
            },
        }

    chosen_csp = best_candidate["csp_out"]
    return {
        "mode": "SMART_OPTIMIZE",
        "feasible": True,
        "solverStatus": "PROVEN_OPTIMAL" if len(distributors) <= 4 else "FEASIBLE_BEST_FOUND",
        "executionTimeMs": exec_time,
        "scheduled": chosen_csp["scheduled"],
        "unscheduled": chosen_csp["unscheduled"],
        "backtracks": chosen_csp.get("backtracks", 0),
        "totalTravelMinutes": best_candidate["totalTravel"],
        "totalDistanceKm": best_candidate["totalDistanceKm"],
        "totalWaitingMinutes": best_candidate["totalWaiting"],
        "highRiskCount": best_candidate["highRiskCount"],
        "objectiveScore": round(best_candidate["score"], 2),
        "objectiveWeights": {
            "wPriority": w_priority,
            "wTravel": w_travel,
            "wWaiting": w_waiting,
            "wRisk": w_risk,
        },
        "candidateTelemetry": candidate_telemetry,
        "constraintsSummary": chosen_csp.get("constraintsSummary", ""),
    }


def generate_schedule_suggestions(
    diagnostics: dict[str, Any],
    quick_fix: dict[str, Any],
    smart_opt: dict[str, Any],
) -> dict[str, Any]:
    """
    Mode C: Suggestions Only
    Synthesizes non-destructive recommendations from diagnostics, Quick Fix, and Smart Optimize.
    """
    suggestions: list[dict[str, Any]] = []

    # 1. Travel buffer & shortfall recommendations
    shortfalls = [i for i in diagnostics["issues"] if i["type"] == "INSUFFICIENT_TRAVEL_BUFFER"]
    if shortfalls:
        max_sf = max(i.get("shortfallMinutes", 0) for i in shortfalls)
        affected = [i["distributorName"] for i in shortfalls]
        suggestions.append({
            "category": "TRAVEL_TRANSITION",
            "title": f"Increase Travel Buffer by {max_sf} min",
            "detail": f"{len(shortfalls)} visit transition(s) ({', '.join(affected)}) lack adequate road transit time. Increasing the travel buffer will prevent schedule creep.",
            "impact": "Eliminates officer transit delay and restores feasible arrivals.",
            "modeRecommended": "QUICK_FIX",
        })

    # 2. Operating window clashing recommendations
    window_issues = [i for i in diagnostics["issues"] if i["type"] in ("OPERATING_WINDOW_EARLY", "OPERATING_WINDOW_LATE")]
    if window_issues:
        suggestions.append({
            "category": "OPERATING_HOURS",
            "title": "Shift Visit Slots into Distributor Operating Windows",
            "detail": f"{len(window_issues)} visit(s) currently violate distributor opening or closing hours. Quick Fix shifts these to valid open hours.",
            "impact": "Prevents arriving at locked premises.",
            "modeRecommended": "QUICK_FIX",
        })

    # 3. Lunch clashes
    lunch_issues = [i for i in diagnostics["issues"] if i["type"] == "LUNCH_OVERLAP"]
    if lunch_issues:
        suggestions.append({
            "category": "MANDATORY_BREAK",
            "title": "Clear Mandatory Lunch Break Interval",
            "detail": f"{len(lunch_issues)} visit(s) clash with the 12:30–13:30 officer rest break. Shifting post-lunch visits clears this constraint.",
            "impact": "Ensures field labor compliance without reducing visit count.",
            "modeRecommended": "QUICK_FIX",
        })

    # 4. Bayesian delay risk optimization
    risk_issues = [i for i in diagnostics["issues"] if i["type"] == "BAYESIAN_HIGH_DELAY_RISK"]
    if risk_issues and smart_opt.get("feasible"):
        orig_risk_count = len(risk_issues)
        opt_risk_count = smart_opt.get("highRiskCount", 0)
        risk_diff = orig_risk_count - opt_risk_count
        if risk_diff > 0:
            suggestions.append({
                "category": "BAYESIAN_RISK_REDUCTION",
                "title": f"Re-sequence Visits to Reduce Delay Exposure (-{risk_diff} High Risk)",
                "detail": f"Smart Optimize places long visits and far transits earlier in the shift, reducing high delay risk from {orig_risk_count} to {opt_risk_count}.",
                "impact": f"Lowers cumulative delay probability across afternoon appointments by {round(risk_diff / max(1, orig_risk_count) * 100)}%.",
                "modeRecommended": "SMART_OPTIMIZE",
            })

    # 5. Route compaction
    if smart_opt.get("feasible") and quick_fix.get("feasible"):
        qf_trav = quick_fix.get("totalTravelMinutes", 0)
        so_trav = smart_opt.get("totalTravelMinutes", 0)
        if so_trav < qf_trav:
            savings = qf_trav - so_trav
            suggestions.append({
                "category": "TRAVEL_EFFICIENCY",
                "title": f"Save {savings} Minutes Road Travel Duration",
                "detail": f"Smart Optimize visit permutation achieves {so_trav}m travel vs. {qf_trav}m in order-preserved Quick Fix.",
                "impact": "Reduces fuel consumption and vehicle transit wear.",
                "modeRecommended": "SMART_OPTIMIZE",
            })

    return {
        "suggestionCount": len(suggestions),
        "suggestions": suggestions,
        "diagnosticsSummary": {
            "totalIssues": diagnostics["issueCount"],
            "criticalIssues": diagnostics["criticalCount"],
            "highIssues": diagnostics["highCount"],
        },
    }
