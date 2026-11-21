from __future__ import annotations

from datetime import date
from app.algorithms.kmeans import run_kmeans
from app.extensions import db
from app.models import Distributor, DistributorCluster, OfficeLocation, RoutePlan


def resolve_workspace_route_plan_id(
    requested_plan_id: str | None, fallback_name: str, plan_date_str: str
) -> str:
    if requested_plan_id:
        existing = db.session.get(RoutePlan, requested_plan_id)
        if existing:
            return str(existing.id)

    named = db.session.query(RoutePlan).filter_by(name=fallback_name).first()
    if named:
        return str(named.id)

    office = (
        db.session.query(OfficeLocation)
        .order_by(OfficeLocation.is_default.desc(), OfficeLocation.created_at.asc())
        .first()
    )
    if office is None:
        raise ValueError("NO_OFFICE_LOCATION")

    plan = RoutePlan(
        name=fallback_name,
        plan_date=date.fromisoformat(plan_date_str),
        office_id=str(office.id),
        travel_mode="simulated_vehicle",
        status="draft",
        map_provider="simulated",
        notes="",
    )
    db.session.add(plan)
    db.session.flush()
    return str(plan.id)


def get_latest_clusters() -> dict | None:
    latest_row = (
        db.session.query(DistributorCluster)
        .filter(DistributorCluster.route_plan_id.isnot(None))
        .order_by(DistributorCluster.created_at.desc())
        .first()
    )
    if latest_row is None:
        return None

    route_plan_id = str(latest_row.route_plan_id)
    clusters = (
        db.session.query(DistributorCluster)
        .filter(DistributorCluster.route_plan_id == route_plan_id)
        .order_by(DistributorCluster.cluster_number.asc())
        .all()
    )

    all_ids = [did for c in clusters for did in (c.distributor_ids or [])]
    dist_map: dict[str, Distributor] = {}
    if all_ids:
        dists = db.session.query(Distributor).filter(Distributor.id.in_(all_ids)).all()
        dist_map = {str(d.id): d for d in dists}

    assignments: list[dict] = []
    centroids: list[dict] = []

    for c in clusters:
        label = c.cluster_label or f"Cluster {c.cluster_number + 1}"
        member_ids = c.distributor_ids or []
        centroids.append(
            {
                "clusterIndex": int(c.cluster_number),
                "clusterLabel": label,
                "centroidLat": float(c.centroid_latitude or 0.0),
                "centroidLng": float(c.centroid_longitude or 0.0),
                "count": len(member_ids),
            }
        )
        for did in member_ids:
            d = dist_map.get(str(did))
            if d:
                assignments.append(
                    {
                        "distributorId": str(d.id),
                        "distributorName": d.name,
                        "latitude": float(d.latitude),
                        "longitude": float(d.longitude),
                        "clusterIndex": int(c.cluster_number),
                        "clusterLabel": label,
                        "distanceToCentroidKm": 0.0,
                    }
                )

    return {
        "routePlanId": route_plan_id,
        "k": len(centroids),
        "centroids": centroids,
        "assignments": assignments,
    }


def run_and_save_clusters(payload: dict) -> dict:
    dist_ids: list[str] = payload["distributorIds"]
    k = int(payload["k"])
    if k > len(dist_ids):
        raise ValueError(
            f"K ({k}) must satisfy 1 <= K <= number of selected distributors ({len(dist_ids)})."
        )

    dists = db.session.query(Distributor).filter(Distributor.id.in_(dist_ids)).all()
    if len(dists) != len(dist_ids):
        raise LookupError("One or more selected distributors do not exist.")

    result = run_kmeans(
        [
            {
                "id": str(d.id),
                "name": d.name,
                "latitude": float(d.latitude),
                "longitude": float(d.longitude),
            }
            for d in dists
        ],
        k=k,
        seed=int(payload.get("seed", 42)),
        max_iterations=int(payload.get("maxIterations", 100)),
        init_method=payload.get("initMethod", "kmeans++"),
    )

    today = date.today().isoformat()
    target_plan_id = resolve_workspace_route_plan_id(
        payload.get("routePlanId"), "K-Means Clustering Workspace", today
    )

    db.session.query(DistributorCluster).filter_by(route_plan_id=target_plan_id).delete()
    for c in result["centroids"]:
        member_ids = [
            a["distributorId"]
            for a in result["assignments"]
            if a["clusterIndex"] == c["clusterIndex"]
        ]
        db.session.add(
            DistributorCluster(
                route_plan_id=target_plan_id,
                cluster_number=c["clusterIndex"],
                cluster_label=c["clusterLabel"],
                centroid_latitude=c["centroidLat"],
                centroid_longitude=c["centroidLng"],
                distributor_ids=member_ids,
            )
        )
    db.session.commit()

    return {"routePlanId": target_plan_id, **result}
