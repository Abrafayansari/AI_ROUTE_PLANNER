from __future__ import annotations

from datetime import date, datetime, timezone
import pandas as pd
from sqlalchemy import func

from app.algorithms import run_astar, run_bfs, run_genetic_algorithm, run_ucs
from app.algorithms.bayesian_network import get_bayesian_network
from app.extensions import db
from app.models import (
    AlgorithmRun,
    Distributor,
    DistributorCluster,
    OfficeLocation,
    RoutePlan,
    RouteStop,
    ScheduleEntry,
    VisitDelayPrediction,
)
from app.utils.metrics import (
    build_local_cost_matrix,
    minutes_to_time,
    time_to_minutes,
)

FIXED_OPTIMIZER_SEED = 42
FIXED_DISTANCE_MULTIPLIER = 1.0
FIXED_GA_POPULATION_SIZE = 80
FIXED_GA_GENERATIONS = 150
FIXED_GA_MUTATION_RATE = 0.18

PREFERENCE_ORDER = {
    "A*": 0,
    "UCS": 1,
    "GENETIC_ALGORITHM": 2,
    "BFS": 3,
}


def _to_utc_dt(plan_date_str: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{plan_date_str}T{hhmm}:00+00:00").astimezone(timezone.utc)


def _build_nodes_and_matrix(
    office_id: str,
    distributor_ids: list[str],
    seed: int = FIXED_OPTIMIZER_SEED,
    distance_multiplier: float = FIXED_DISTANCE_MULTIPLIER,
    travel_mode: str = "simulated_vehicle",
):
    office = db.session.get(OfficeLocation, office_id)
    if office is None:
        raise FileNotFoundError("Office location not found.")

    dists = db.session.query(Distributor).filter(Distributor.id.in_(distributor_ids)).all()
    if len(dists) != len(distributor_ids):
        raise LookupError("One or more selected distributors do not exist.")

    dist_map = {str(d.id): d for d in dists}
    ordered_dists = [dist_map[did] for did in distributor_ids]

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
            "visitDurationMinutes": int(d.visit_duration_minutes),
            "priority": int(d.priority),
        }
        for d in ordered_dists
    ]

    matrix = build_local_cost_matrix(
        nodes,
        seed=seed,
        distance_multiplier=distance_multiplier,
        travel_mode=travel_mode,  # type: ignore[arg-type]
    )
    return office, ordered_dists, nodes, matrix


def _select_recommended_run(runs: list[dict]) -> dict:
    completed = [r for r in runs if r.get("completed") and r.get("routeOrder")]
    if not completed:
        raise RuntimeError("No algorithm completed a valid route.")
    return sorted(
        completed,
        key=lambda r: (
            round(float(r["estimatedDistanceKm"]), 6),
            PREFERENCE_ORDER.get(r["algorithm"], 9),
        ),
    )[0]


def generate_local_matrix(payload: dict) -> dict:
    _, _, _, matrix = _build_nodes_and_matrix(
        office_id=payload["officeId"],
        distributor_ids=payload["distributorIds"],
        seed=FIXED_OPTIMIZER_SEED,
        distance_multiplier=FIXED_DISTANCE_MULTIPLIER,
        travel_mode=payload.get("travelMode", "simulated_vehicle"),
    )
    return {
        **matrix.to_dict(),
        "disclaimer": (
            "Locally generated simulated distance matrix using Haversine coordinates "
            "and deterministic multiplier. Not real road distances or live traffic."
        ),
    }


def preview_optimization(payload: dict) -> dict:
    _, _, nodes, matrix = _build_nodes_and_matrix(
        office_id=payload["officeId"],
        distributor_ids=payload["distributorIds"],
        seed=FIXED_OPTIMIZER_SEED,
        distance_multiplier=FIXED_DISTANCE_MULTIPLIER,
        travel_mode=payload.get("travelMode", "simulated_vehicle"),
    )

    return_to_office = bool(payload.get("returnToOffice", True))
    bfs = run_bfs(matrix, return_to_office)
    ucs = run_ucs(matrix, return_to_office)
    astar = run_astar(matrix, return_to_office)
    ga = run_genetic_algorithm(
        matrix,
        return_to_office,
        seed=FIXED_OPTIMIZER_SEED,
        population_size=FIXED_GA_POPULATION_SIZE,
        generations=FIXED_GA_GENERATIONS,
        mutation_rate=FIXED_GA_MUTATION_RATE,
    )

    all_runs = [bfs, ucs, astar, ga]
    completed = [r for r in all_runs if r.get("completed") and r.get("routeOrder")]
    recommended = _select_recommended_run(completed) if completed else None

    # Calculate preview delay predictions for the recommended tour
    preview_delay_predictions = []
    if recommended:
        bn = get_bayesian_network()
        clock_min = time_to_minutes("09:00")
        for stop_idx, node_idx in enumerate(recommended["routeOrder"]):
            if nodes[node_idx]["isOffice"]:
                continue
            prev_idx = recommended["routeOrder"][stop_idx - 1] if stop_idx > 0 else 0
            leg_dist = matrix.distanceKm[prev_idx][node_idx]
            leg_dur = matrix.durationMinutes[prev_idx][node_idx]
            clock_min += round(leg_dur)
            arr_time_str = minutes_to_time(clock_min)
            node_data = nodes[node_idx]
            clock_min += int(node_data.get("visitDurationMinutes", 30))

            pred = bn.predict_visit(
                distributor_id=node_data["id"],
                distributor_name=node_data["name"],
                distance_km=round(leg_dist, 2),
                visit_duration_minutes=int(node_data.get("visitDurationMinutes", 30)),
                time_slot_raw=arr_time_str,
                priority_raw=node_data.get("priority"),
                stop_order=stop_idx,
            )
            preview_delay_predictions.append(pred)

    return {
        "nodes": nodes,
        "matrix": {
            "distanceKm": matrix.distanceKm,
            "durationMinutes": matrix.durationMinutes,
            "straightLineKm": matrix.straightLineKm,
            "cacheHit": matrix.cacheHit,
            "speedKmh": matrix.speedKmh,
            "seed": matrix.seed,
            "distanceMultiplier": matrix.distanceMultiplier,
            "travelMode": matrix.travelMode,
        },
        "recommendedAlgorithm": recommended["algorithm"] if recommended else None,
        "results": all_runs,
        "delayPredictions": preview_delay_predictions,
    }


def list_route_plans(page: int = 1, page_size: int = 20) -> dict:
    total = db.session.query(RoutePlan).count()
    offset = (page - 1) * page_size
    plans = (
        db.session.query(RoutePlan)
        .order_by(RoutePlan.created_at.desc())
        .limit(page_size)
        .offset(offset)
        .all()
    )

    items = []
    for p in plans:
        stop_count = (
            db.session.query(RouteStop)
            .filter(
                RouteStop.route_plan_id == p.id,
                RouteStop.distributor_id.isnot(None),
            )
            .count()
        )
        visited_count = (
            db.session.query(RouteStop)
            .filter(
                RouteStop.route_plan_id == p.id,
                RouteStop.distributor_id.isnot(None),
                RouteStop.status == "visited",
            )
            .count()
        )
        items.append(p.to_dict(stop_count=stop_count, visited_count=visited_count))

    return {
        "items": items,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": max(1, (total + page_size - 1) // page_size),
        },
    }


def create_route_plan(payload: dict) -> dict:
    office = db.session.get(OfficeLocation, payload["officeId"])
    if office is None:
        raise FileNotFoundError("Office location not found.")

    dist_ids: list[str] = payload["distributorIds"]
    dists = db.session.query(Distributor).filter(Distributor.id.in_(dist_ids)).all()
    if len(dists) != len(dist_ids):
        raise LookupError("One or more selected distributors do not exist.")
    dist_map = {str(d.id): d for d in dists}

    plan = RoutePlan(
        name=payload["name"],
        plan_date=date.fromisoformat(payload["planDate"]),
        office_id=str(office.id),
        travel_mode=payload.get("travelMode", "simulated_vehicle"),
        return_to_office=bool(payload.get("returnToOffice", True)),
        distance_multiplier=FIXED_DISTANCE_MULTIPLIER,
        graph_seed=FIXED_OPTIMIZER_SEED,
        status="draft",
        map_provider="simulated",
        notes=payload.get("notes", ""),
    )
    db.session.add(plan)
    db.session.flush()

    order_idx = 1
    db.session.add(
        RouteStop(
            route_plan_id=str(plan.id),
            distributor_id=None,
            stop_order=order_idx,
            stop_name=f"{office.name} (Start)",
            latitude=float(office.latitude),
            longitude=float(office.longitude),
            travel_from_previous_minutes=0,
            distance_from_previous_km=0.0,
            visit_duration_minutes=0,
            status="pending",
        )
    )
    order_idx += 1

    for did in dist_ids:
        d = dist_map[did]
        db.session.add(
            RouteStop(
                route_plan_id=str(plan.id),
                distributor_id=str(d.id),
                stop_order=order_idx,
                stop_name=d.name,
                latitude=float(d.latitude),
                longitude=float(d.longitude),
                visit_duration_minutes=int(d.visit_duration_minutes),
                status="pending",
            )
        )
        order_idx += 1

    if plan.return_to_office:
        db.session.add(
            RouteStop(
                route_plan_id=str(plan.id),
                distributor_id=None,
                stop_order=order_idx,
                stop_name=f"{office.name} (Return)",
                latitude=float(office.latitude),
                longitude=float(office.longitude),
                visit_duration_minutes=0,
                status="pending",
            )
        )

    db.session.commit()
    return plan.to_dict()


def _write_stops_for_route(
    plan_id: str,
    plan_date_str: str,
    route_order: list[int],
    nodes: list[dict],
    matrix,
    return_to_office: bool,
) -> None:
    db.session.query(RouteStop).filter_by(route_plan_id=plan_id).delete()
    clock_min = time_to_minutes("09:00")

    for idx, node_idx in enumerate(route_order):
        prev_idx = route_order[idx - 1] if idx > 0 else node_idx
        leg_dist = matrix.distanceKm[prev_idx][node_idx] if idx > 0 else 0.0
        leg_dur = matrix.durationMinutes[prev_idx][node_idx] if idx > 0 else 0.0

        clock_min += round(leg_dur)
        arr_str = minutes_to_time(clock_min)
        visit_dur = (
            0
            if nodes[node_idx]["isOffice"]
            else int(nodes[node_idx].get("visitDurationMinutes", 30))
        )
        clock_min += visit_dur
        dep_str = minutes_to_time(clock_min)

        is_office_stop = idx == 0 or (
            return_to_office and idx == len(route_order) - 1
        )
        stop_name = (
            f"{nodes[node_idx]['name']} ({'Start' if idx == 0 else 'Return'})"
            if is_office_stop
            else nodes[node_idx]["name"]
        )

        db.session.add(
            RouteStop(
                route_plan_id=plan_id,
                distributor_id=None if is_office_stop else nodes[node_idx]["id"],
                stop_order=idx + 1,
                stop_name=stop_name,
                latitude=float(nodes[node_idx]["latitude"]),
                longitude=float(nodes[node_idx]["longitude"]),
                estimated_arrival=_to_utc_dt(plan_date_str, arr_str),
                estimated_departure=_to_utc_dt(plan_date_str, dep_str),
                travel_from_previous_minutes=round(leg_dur),
                distance_from_previous_km=round(leg_dist, 3),
                visit_duration_minutes=visit_dur,
                status="pending",
            )
        )


def optimize_route_plan(plan_id: str, payload: dict) -> dict:
    plan = db.session.get(RoutePlan, plan_id)
    if plan is None:
        raise FileNotFoundError("Route plan not found.")

    plan_date_str = plan.plan_date.isoformat() if isinstance(plan.plan_date, date) else str(plan.plan_date)[:10]

    distributor_ids = payload.get("distributorIds")
    if not distributor_ids:
        stops = (
            db.session.query(RouteStop)
            .filter(
                RouteStop.route_plan_id == plan_id,
                RouteStop.distributor_id.isnot(None),
            )
            .order_by(RouteStop.stop_order.asc())
            .all()
        )
        seen: set[str] = set()
        distributor_ids = []
        for s in stops:
            did = str(s.distributor_id)
            if did not in seen:
                seen.add(did)
                distributor_ids.append(did)

    if not distributor_ids:
        raise ValueError("Route plan has no distributors to optimize.")

    seed = FIXED_OPTIMIZER_SEED
    distance_multiplier = FIXED_DISTANCE_MULTIPLIER
    return_to_office = bool(
        payload["returnToOffice"]
        if payload.get("returnToOffice") is not None
        else plan.return_to_office
    )
    travel_mode = payload.get("travelMode") or plan.travel_mode or "simulated_vehicle"

    _, _, nodes, matrix = _build_nodes_and_matrix(
        office_id=str(plan.office_id),
        distributor_ids=distributor_ids,
        seed=seed,
        distance_multiplier=distance_multiplier,
        travel_mode=travel_mode,
    )

    bfs = run_bfs(matrix, return_to_office)
    ucs = run_ucs(matrix, return_to_office)
    astar = run_astar(matrix, return_to_office)
    ga = run_genetic_algorithm(
        matrix,
        return_to_office,
        seed=seed,
        population_size=FIXED_GA_POPULATION_SIZE,
        generations=FIXED_GA_GENERATIONS,
        mutation_rate=FIXED_GA_MUTATION_RATE,
    )

    all_runs = [bfs, ucs, astar, ga]
    recommended_run = _select_recommended_run(all_runs)
    chosen_name = payload.get("selectedAlgorithm") or recommended_run["algorithm"]
    chosen_run = next(
        (r for r in all_runs if r["algorithm"] == chosen_name and r.get("completed")),
        recommended_run,
    )

    db.session.query(AlgorithmRun).filter_by(route_plan_id=plan_id).delete()
    for r in all_runs:
        route_uuids = [nodes[idx]["id"] for idx in r["routeOrder"]]
        route_names = [
            {
                "nodeIndex": idx,
                "id": nodes[idx]["id"],
                "name": nodes[idx]["name"],
                "isOffice": bool(nodes[idx]["isOffice"]),
            }
            for idx in r["routeOrder"]
        ]
        params = {
            "seed": seed,
            "distanceMultiplier": distance_multiplier,
            "travelMode": travel_mode,
            "returnToOffice": return_to_office,
            **(ga["parameters"] if r["algorithm"] == "GENETIC_ALGORITHM" else {}),
        }
        details = {
            "isInformed": bool(r["isInformed"]),
            "isRecommended": r["algorithm"] == recommended_run["algorithm"],
            "objectiveDescription": r["objectiveDescription"],
            "edgeCount": r["edgeCount"],
            "isOptimalForObjective": bool(r["isOptimalForObjective"]),
            **(
                {
                    "generationsRun": ga["generationsRun"],
                    "convergenceHistory": ga["convergenceHistory"],
                }
                if r["algorithm"] == "GENETIC_ALGORITHM"
                else {}
            ),
        }

        db.session.add(
            AlgorithmRun(
                route_plan_id=plan_id,
                algorithm_name=r["algorithm"],
                status="completed" if r["completed"] else "failed",
                route_order=route_uuids,
                route_names=route_names,
                total_cost=r["totalCost"],
                total_distance_km=r["estimatedDistanceKm"],
                estimated_duration_minutes=round(r["estimatedDurationMinutes"]),
                nodes_expanded=r["nodesExpanded"],
                execution_time_ms=r["executionTimeMs"],
                parameters=params,
                result_details=details,
                error_message=r.get("warning"),
            )
        )

    _write_stops_for_route(
        plan_id=plan_id,
        plan_date_str=plan_date_str,
        route_order=chosen_run["routeOrder"],
        nodes=nodes,
        matrix=matrix,
        return_to_office=return_to_office,
    )

    plan.recommended_algorithm = recommended_run["algorithm"]
    plan.selected_algorithm = chosen_run["algorithm"]
    plan.total_distance_km = chosen_run["estimatedDistanceKm"]
    plan.total_duration_minutes = round(chosen_run["estimatedDurationMinutes"])
    plan.distance_multiplier = distance_multiplier
    plan.graph_seed = seed
    plan.return_to_office = return_to_office
    plan.travel_mode = travel_mode
    plan.status = "optimized"
    plan.updated_at = datetime.now(timezone.utc)

    # Evaluate and persist Bayesian delay predictions for the optimized route
    from app.services.prediction_service import predict_route_plan_delays
    delay_results = predict_route_plan_delays(plan_id, save_to_db=True)

    return {
        "routePlanId": plan_id,
        "recommendedAlgorithm": recommended_run["algorithm"],
        "selectedAlgorithm": chosen_run["algorithm"],
        "matrixCacheHit": matrix.cacheHit,
        "speedKmh": matrix.speedKmh,
        "nodes": nodes,
        "results": all_runs,
        "delayRiskSummary": delay_results.get("summary"),
        "delayPredictions": delay_results.get("predictions", []),
    }


def get_route_plan_detail(plan_id: str) -> dict:
    plan = db.session.get(RoutePlan, plan_id)
    if plan is None:
        raise FileNotFoundError("Route plan not found.")

    stops = (
        db.session.query(RouteStop)
        .filter_by(route_plan_id=plan_id)
        .order_by(RouteStop.stop_order.asc())
        .all()
    )
    algos = (
        db.session.query(AlgorithmRun)
        .filter_by(route_plan_id=plan_id)
        .order_by(AlgorithmRun.total_distance_km.asc().nullslast())
        .all()
    )
    schedules = (
        db.session.query(ScheduleEntry)
        .filter_by(route_plan_id=plan_id)
        .order_by(ScheduleEntry.scheduled_start.asc())
        .all()
    )
    delay_predictions = (
        db.session.query(VisitDelayPrediction)
        .filter_by(route_plan_id=plan_id)
        .order_by(VisitDelayPrediction.stop_order.asc())
        .all()
    )

    return {
        "plan": plan.to_dict(include_office_address=True),
        "stops": [s.to_dict() for s in stops],
        "algorithms": [a.to_dict() for a in algos],
        "scheduleEntries": [s.to_dict() for s in schedules],
        "delayPredictions": [p.to_dict() for p in delay_predictions],
    }


def get_route_plan_algorithms(plan_id: str) -> list[dict]:
    algos = (
        db.session.query(AlgorithmRun)
        .filter_by(route_plan_id=plan_id)
        .order_by(AlgorithmRun.total_distance_km.asc().nullslast())
        .all()
    )
    return [a.to_dict() for a in algos]


def update_route_plan(plan_id: str, payload: dict) -> dict:
    plan = db.session.get(RoutePlan, plan_id)
    if plan is None:
        raise FileNotFoundError("Route plan not found.")

    plan_date_str = (
        plan.plan_date.isoformat()
        if isinstance(plan.plan_date, date)
        else str(plan.plan_date)[:10]
    )

    if payload.get("selectedAlgorithm"):
        algo_row = (
            db.session.query(AlgorithmRun)
            .filter_by(
                route_plan_id=plan_id, algorithm_name=payload["selectedAlgorithm"]
            )
            .first()
        )
        if algo_row and isinstance(algo_row.route_names, list):
            ordered_nodes = algo_row.route_names
            dist_ids = list(
                dict.fromkeys(
                    n["id"] for n in ordered_nodes if not n.get("isOffice")
                )
            )
            office, unique_dists, graph_nodes, matrix = _build_nodes_and_matrix(
                office_id=str(plan.office_id),
                distributor_ids=dist_ids,
                seed=int(plan.graph_seed or 42),
                distance_multiplier=float(plan.distance_multiplier or 1.25),
                travel_mode=plan.travel_mode or "simulated_vehicle",
            )
            node_idx_by_id = {n["id"]: idx for idx, n in enumerate(graph_nodes)}
            route_order = [
                0 if n.get("isOffice") else node_idx_by_id.get(n["id"], 0)
                for n in ordered_nodes
            ]
            _write_stops_for_route(
                plan_id=plan_id,
                plan_date_str=plan_date_str,
                route_order=route_order,
                nodes=graph_nodes,
                matrix=matrix,
                return_to_office=bool(plan.return_to_office),
            )
            plan.total_distance_km = float(algo_row.total_distance_km or 0.0)
            plan.total_duration_minutes = int(algo_row.estimated_duration_minutes or 0)
            plan.selected_algorithm = payload["selectedAlgorithm"]

    if payload.get("name") is not None:
        plan.name = payload["name"]
    if payload.get("planDate") is not None:
        plan.plan_date = date.fromisoformat(payload["planDate"])
    if payload.get("status") is not None:
        plan.status = payload["status"]
    if payload.get("notes") is not None:
        plan.notes = payload["notes"]

    plan.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return plan.to_dict()


def delete_route_plan(plan_id: str) -> bool:
    plan = db.session.get(RoutePlan, plan_id)
    if plan is None:
        return False
    db.session.delete(plan)
    db.session.commit()
    return True


def update_stop_status(stop_id: str, status: str) -> dict | None:
    stop = db.session.get(RouteStop, stop_id)
    if stop is None:
        return None

    stop.status = status
    plan_id = str(stop.route_plan_id)

    total = (
        db.session.query(RouteStop)
        .filter(
            RouteStop.route_plan_id == plan_id,
            RouteStop.distributor_id.isnot(None),
        )
        .count()
    )
    done = (
        db.session.query(RouteStop)
        .filter(
            RouteStop.route_plan_id == plan_id,
            RouteStop.distributor_id.isnot(None),
            RouteStop.status.in_(["visited", "skipped"]),
        )
        .count()
    )

    next_status = (
        "completed"
        if (total > 0 and done == total)
        else ("in_progress" if done > 0 else "optimized")
    )

    plan = db.session.get(RoutePlan, plan_id)
    if plan and plan.status != "draft":
        plan.status = next_status
        plan.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    return {
        "stop": {
            "id": str(stop.id),
            "route_plan_id": plan_id,
            "status": stop.status,
        },
        "planStatus": next_status,
    }


def get_analytics_summary() -> dict:
    total_distributors = db.session.query(Distributor).count()
    active_distributors = db.session.query(Distributor).filter_by(is_active=True).count()
    demo_distributors = db.session.query(Distributor).filter_by(is_demo=True).count()

    total_plans = db.session.query(RoutePlan).count()
    scheduled_or_completed = (
        db.session.query(RoutePlan)
        .filter(RoutePlan.status.in_(["scheduled", "completed", "optimized", "in_progress"]))
        .count()
    )

    avg_dist_val = (
        db.session.query(func.avg(RoutePlan.total_distance_km))
        .filter(RoutePlan.total_distance_km > 0)
        .scalar()
    )
    avg_dur_val = (
        db.session.query(func.avg(RoutePlan.total_duration_minutes))
        .filter(RoutePlan.total_duration_minutes > 0)
        .scalar()
    )
    avg_distance_km = round(float(avg_dist_val), 2) if avg_dist_val is not None else None
    avg_duration_minutes = round(float(avg_dur_val), 1) if avg_dur_val is not None else None

    latest_plan_obj = (
        db.session.query(RoutePlan).order_by(RoutePlan.created_at.desc()).first()
    )
    latest_plan = latest_plan_obj.to_dict() if latest_plan_obj else None

    # Use Pandas for clean aggregation over completed algorithm runs
    completed_runs = (
        db.session.query(AlgorithmRun)
        .filter_by(status="completed")
        .all()
    )

    algorithm_averages: list[dict] = []
    if completed_runs:
        df = pd.DataFrame(
            [
                {
                    "algorithm_name": r.algorithm_name,
                    "total_cost": float(r.total_cost or 0.0),
                    "total_distance_km": float(r.total_distance_km or 0.0),
                    "estimated_duration_minutes": float(r.estimated_duration_minutes or 0.0),
                    "nodes_expanded": float(r.nodes_expanded or 0.0),
                    "execution_time_ms": float(r.execution_time_ms or 0.0),
                }
                for r in completed_runs
            ]
        )
        grouped = (
            df.groupby("algorithm_name", as_index=False)
            .agg(
                run_count=("algorithm_name", "count"),
                avg_cost=("total_cost", "mean"),
                avg_distance=("total_distance_km", "mean"),
                avg_duration=("estimated_duration_minutes", "mean"),
                avg_nodes_expanded=("nodes_expanded", "mean"),
                avg_exec_ms=("execution_time_ms", "mean"),
            )
            .sort_values("avg_distance", ascending=True)
        )
        for row in grouped.to_dict(orient="records"):
            algorithm_averages.append(
                {
                    "algorithmName": row["algorithm_name"],
                    "runCount": int(row["run_count"]),
                    "avgCost": round(float(row["avg_cost"]), 2),
                    "avgDistanceKm": round(float(row["avg_distance"]), 2),
                    "avgDurationMinutes": round(float(row["avg_duration"]), 1),
                    "avgNodesExpanded": round(float(row["avg_nodes_expanded"])),
                    "avgExecutionMs": round(float(row["avg_exec_ms"]), 3),
                }
            )

    recent_rows = (
        db.session.query(AlgorithmRun, RoutePlan.name)
        .join(RoutePlan, RoutePlan.id == AlgorithmRun.route_plan_id)
        .order_by(AlgorithmRun.created_at.desc())
        .limit(12)
        .all()
    )
    recent_algorithm_runs = [
        run.to_dict(route_plan_name=plan_name) for run, plan_name in recent_rows
    ]

    latest_cluster_plan = (
        db.session.query(DistributorCluster.route_plan_id)
        .filter(DistributorCluster.route_plan_id.isnot(None))
        .order_by(DistributorCluster.created_at.desc())
        .first()
    )
    latest_clusters_list: list[dict] = []
    if latest_cluster_plan:
        cluster_rows = (
            db.session.query(DistributorCluster)
            .filter_by(route_plan_id=latest_cluster_plan[0])
            .order_by(DistributorCluster.cluster_number.asc())
            .all()
        )
        for c in cluster_rows:
            latest_clusters_list.append(
                {
                    "clusterLabel": c.cluster_label or f"Cluster {c.cluster_number + 1}",
                    "clusterIndex": int(c.cluster_number),
                    "size": len(c.distributor_ids or []),
                }
            )

    latest_sched_plan = (
        db.session.query(ScheduleEntry.route_plan_id)
        .filter(
            ScheduleEntry.route_plan_id.isnot(None),
            ScheduleEntry.scheduled_start.isnot(None),
        )
        .order_by(ScheduleEntry.created_at.desc())
        .first()
    )
    scheduled_count = 0
    schedule_date_str = None
    if latest_sched_plan:
        sched_entries = (
            db.session.query(ScheduleEntry)
            .filter_by(route_plan_id=latest_sched_plan[0])
            .all()
        )
        scheduled_count = len(sched_entries)
        if sched_entries and sched_entries[0].scheduled_start:
            st = sched_entries[0].scheduled_start
            schedule_date_str = (
                st.date().isoformat() if isinstance(st, datetime) else str(st)[:10]
            )

    unscheduled_estimate = max(0, active_distributors - scheduled_count)

    insights: list[str] = []
    if total_distributors == 0:
        insights.append(
            "No distributors are stored yet. Add distributors or load the demo dataset to begin."
        )
    else:
        insights.append(
            f"There are {active_distributors} active distributor(s) out of {total_distributors} total stored in Neon PostgreSQL."
        )

    if algorithm_averages:
        best_dist = min(algorithm_averages, key=lambda a: a["avgDistanceKm"])
        total_algo_runs = sum(a["runCount"] for a in algorithm_averages)
        insights.append(
            f"Across {total_algo_runs} saved algorithm runs, {best_dist['algorithmName']} achieved the lowest average simulated route distance ({best_dist['avgDistanceKm']} km)."
        )
        astar = next((a for a in algorithm_averages if a["algorithmName"] == "A*"), None)
        ucs = next((a for a in algorithm_averages if a["algorithmName"] == "UCS"), None)
        bfs = next((a for a in algorithm_averages if a["algorithmName"] == "BFS"), None)
        if astar and ucs and ucs["avgNodesExpanded"] > 0:
            reduction = round(
                ((ucs["avgNodesExpanded"] - astar["avgNodesExpanded"]) / ucs["avgNodesExpanded"])
                * 100
            )
            diff_label = f"{reduction}% fewer expansions" if reduction >= 0 else "similar expansions"
            insights.append(
                f"A* expanded an average of {astar['avgNodesExpanded']} nodes compared to {ucs['avgNodesExpanded']} for Uniform Cost Search ({diff_label}) while achieving the same optimal tour cost."
            )
        if bfs and bfs["avgDistanceKm"] > best_dist["avgDistanceKm"]:
            insights.append(
                f"Unweighted BFS averaged {bfs['avgDistanceKm']} km because BFS minimizes edge/hop count rather than simulated travel distance."
            )
    else:
        insights.append(
            "No route algorithm comparisons have been saved yet. Run the Route Optimizer on a route plan to populate algorithm telemetry."
        )

    if latest_clusters_list:
        insights.append(
            f"Latest K-Means clustering partitioned distributors into {len(latest_clusters_list)} geographic group(s)."
        )
    else:
        insights.append("No K-Means clustering run has been saved yet.")

    if scheduled_count > 0:
        insights.append(
            f"Latest CSP schedule placed {scheduled_count} visit(s) on {schedule_date_str} without overlapping time slots."
        )
    else:
        insights.append("No CSP visit schedule has been saved yet.")

    return {
        "counts": {
            "totalDistributors": total_distributors,
            "activeDistributors": active_distributors,
            "demoDistributors": demo_distributors,
            "totalRoutePlans": total_plans,
            "scheduledOrCompletedPlans": scheduled_or_completed,
            "avgDistanceKm": avg_distance_km,
            "avgDurationMinutes": avg_duration_minutes,
        },
        "latestRoutePlan": latest_plan,
        "algorithmAverages": algorithm_averages,
        "recentAlgorithmRuns": recent_algorithm_runs,
        "latestClusters": latest_clusters_list,
        "scheduleSummary": {
            "hasRun": scheduled_count > 0,
            "scheduledCount": scheduled_count,
            "remainingActiveCount": unscheduled_estimate,
            "scheduleDate": schedule_date_str,
        },
        "plainLanguageSummary": insights,
    }
