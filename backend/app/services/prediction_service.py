from __future__ import annotations

from typing import Any
from sqlalchemy import func

from app.algorithms.bayesian_network import (
    DEFAULT_CPT,
    DEFAULT_PRIORS,
    DEFAULT_THRESHOLDS,
    MODEL_STATUS,
    MODEL_VERSION,
    VALIDATION_STATUS,
    categorize_distance,
    categorize_priority,
    categorize_time_slot,
    categorize_visit_duration,
    get_bayesian_network,
)
from app.extensions import db
from app.models import Distributor, RoutePlan, RouteStop, VisitDelayPrediction
from app.utils.metrics import haversine_distance_km


def get_model_info() -> dict[str, Any]:
    """Return Bayesian Network metadata, variables, topology, and priors."""
    bn = get_bayesian_network()
    info = bn.get_structure_info()
    return {
        "modelVersion": MODEL_VERSION,
        "modelStatus": MODEL_STATUS,
        "validationStatus": VALIDATION_STATUS,
        "variables": [
            {
                "name": "Distance",
                "role": "parent",
                "description": "Transit distance from previous stop (km)",
                "states": ["Near", "Medium", "Far"],
                "thresholds": DEFAULT_THRESHOLDS["distance_km"],
                "priors": DEFAULT_PRIORS["Distance"],
            },
            {
                "name": "VisitDuration",
                "role": "parent",
                "description": "Expected on-site visit duration (minutes)",
                "states": ["Short", "Medium", "Long"],
                "thresholds": DEFAULT_THRESHOLDS["visit_duration_minutes"],
                "priors": DEFAULT_PRIORS["VisitDuration"],
            },
            {
                "name": "TimeSlot",
                "role": "parent",
                "description": "Scheduled time of visit (Morning < 12:30, Afternoon >= 12:30)",
                "states": ["Morning", "Afternoon"],
                "thresholds": DEFAULT_THRESHOLDS["time_slot"],
                "priors": DEFAULT_PRIORS["TimeSlot"],
            },
            {
                "name": "Priority",
                "role": "parent",
                "description": "Distributor priority level (1–5)",
                "states": ["Low", "Medium", "High"],
                "thresholds": DEFAULT_THRESHOLDS["priority"],
                "priors": DEFAULT_PRIORS["Priority"],
            },
            {
                "name": "DelayRisk",
                "role": "target",
                "description": "Predicted visit delay risk posterior distribution",
                "states": ["Low", "Medium", "High"],
                "parents": ["Distance", "VisitDuration", "TimeSlot", "Priority"],
            },
        ],
        "topology": info["topology"],
        "thresholds": DEFAULT_THRESHOLDS,
        "totalCptConfigurations": len(DEFAULT_CPT),
    }


def get_cpt_data() -> dict[str, Any]:
    """Return all 54 rows of the Conditional Probability Table for inspection."""
    rows = []
    for idx, (parents, probs) in enumerate(DEFAULT_CPT.items(), 1):
        dist, dur, ts, prio = parents
        rows.append(
            {
                "id": idx,
                "distance": dist,
                "visitDuration": dur,
                "timeSlot": ts,
                "priority": prio,
                "pLow": probs["Low"],
                "pMedium": probs["Medium"],
                "pHigh": probs["High"],
                "mostLikely": "High" if probs["High"] > probs["Medium"] and probs["High"] > probs["Low"] else ("Medium" if probs["Medium"] > probs["Low"] else "Low"),
            }
        )

    return {
        "modelVersion": MODEL_VERSION,
        "totalRows": len(rows),
        "validationStatus": VALIDATION_STATUS,
        "rows": rows,
    }


def predict_single_visit(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Calculate delay probabilities for a single distributor given supplied evidence
    or by looking up the distributor in the database. Supports partial evidence
    via Bayesian marginalization over unobserved parents.
    """
    bn = get_bayesian_network()

    distributor_id = payload.get("distributorId")
    distributor = None
    if distributor_id:
        distributor = db.session.get(Distributor, distributor_id)

    name = payload.get("distributorName") or (distributor.name if distributor else "Distributor")
    distance_km = payload.get("distanceKm")

    visit_dur = payload.get("visitDurationMinutes")
    if (
        visit_dur is None
        and payload.get("visitDurationCategory") is None
        and distributor is not None
    ):
        visit_dur = distributor.visit_duration_minutes

    raw_ts = payload.get("timeSlotRaw") or payload.get("timeSlot")
    ts_category = payload.get("timeSlot") if payload.get("timeSlot") in ("Morning", "Afternoon") else None
    if raw_ts == "Unobserved":
        raw_ts = None

    priority = payload.get("priority")
    if priority is None:
        priority = payload.get("priorityRaw")
    if (
        priority is None
        and payload.get("priorityCategory") is None
        and distributor is not None
    ):
        priority = distributor.priority

    prediction = bn.predict_visit(
        distributor_id=distributor_id,
        distributor_name=name,
        distance_km=distance_km,
        visit_duration_minutes=visit_dur,
        time_slot_raw=raw_ts,
        priority_raw=priority,
        distance_category=payload.get("distanceCategory"),
        visit_duration_category=payload.get("visitDurationCategory"),
        time_slot=ts_category,
        priority_category=payload.get("priorityCategory"),
        stop_order=payload.get("stopOrder"),
        route_plan_id=payload.get("routePlanId"),
        allow_partial=True,
    )

    # Optionally persist if requested
    if payload.get("saveToDb"):
        db_record = VisitDelayPrediction(
            route_plan_id=payload.get("routePlanId"),
            distributor_id=distributor_id if distributor is not None else None,
            distributor_name=name,
            stop_order=payload.get("stopOrder"),
            distance_km=distance_km,
            distance_category=prediction["evidence"]["distanceCategory"],
            visit_duration_minutes=visit_dur,
            visit_duration_category=prediction["evidence"]["visitDurationCategory"],
            time_slot=prediction["evidence"]["timeSlot"],
            priority_category=prediction["evidence"]["priorityCategory"],
            probability_low=prediction["probabilities"]["Low"],
            probability_medium=prediction["probabilities"]["Medium"],
            probability_high=prediction["probabilities"]["High"],
            predicted_risk=prediction["predictedRisk"],
            recommended_buffer_minutes=prediction["recommendedBufferMinutes"],
            recommendation_note=prediction.get("recommendation"),
            model_version=prediction["modelVersion"],
            model_status=prediction["modelStatus"],
        )
        db.session.add(db_record)
        db.session.commit()
        prediction["id"] = str(db_record.id)

    return prediction


def predict_route_plan_delays(route_plan_id: str, save_to_db: bool = True) -> dict[str, Any]:
    """
    Calculate delay probabilities for all stops in a saved route plan in Neon PostgreSQL.
    """
    plan = db.session.get(RoutePlan, route_plan_id)
    if plan is None:
        raise FileNotFoundError("Route plan not found.")

    stops = (
        db.session.query(RouteStop)
        .filter(
            RouteStop.route_plan_id == route_plan_id,
            RouteStop.distributor_id.isnot(None),
        )
        .order_by(RouteStop.stop_order.asc())
        .all()
    )

    if not stops:
        raise ValueError("Route plan has no distributor stops to evaluate.")

    bn = get_bayesian_network()
    predictions = []
    low_count = 0
    med_count = 0
    high_count = 0

    if save_to_db:
        # Clear prior predictions for this route plan to avoid duplicate history
        db.session.query(VisitDelayPrediction).filter_by(route_plan_id=route_plan_id).delete()

    for s in stops:
        dist = s.distributor
        priority_val = dist.priority if dist else 3

        # Resolve distance: prefer distance_from_previous_km, or straight-line
        dist_km = float(s.distance_from_previous_km) if s.distance_from_previous_km is not None else 5.0
        dur_min = int(s.visit_duration_minutes or (dist.visit_duration_minutes if dist else 30))

        # Time slot from estimated arrival
        time_val = s.estimated_arrival or "10:00"

        pred = bn.predict_visit(
            distributor_id=str(s.distributor_id),
            distributor_name=s.stop_name,
            distance_km=dist_km,
            visit_duration_minutes=dur_min,
            time_slot_raw=time_val,
            priority_raw=priority_val,
            stop_order=int(s.stop_order),
            route_plan_id=route_plan_id,
        )

        risk = pred["predictedRisk"]
        if risk == "High":
            high_count += 1
        elif risk == "Medium":
            med_count += 1
        else:
            low_count += 1

        if save_to_db:
            db_rec = VisitDelayPrediction(
                route_plan_id=route_plan_id,
                distributor_id=str(s.distributor_id),
                distributor_name=s.stop_name,
                stop_order=int(s.stop_order),
                distance_km=dist_km,
                distance_category=pred["evidence"]["distanceCategory"],
                visit_duration_minutes=dur_min,
                visit_duration_category=pred["evidence"]["visitDurationCategory"],
                time_slot=pred["evidence"]["timeSlot"],
                priority_category=pred["evidence"]["priorityCategory"],
                probability_low=pred["probabilities"]["Low"],
                probability_medium=pred["probabilities"]["Medium"],
                probability_high=pred["probabilities"]["High"],
                predicted_risk=risk,
                recommended_buffer_minutes=pred["recommendedBufferMinutes"],
                recommendation_note=pred.get("recommendation"),
                model_version=pred["modelVersion"],
                model_status=pred["modelStatus"],
            )
            db.session.add(db_rec)
            pred["id"] = str(db_rec.id)

        predictions.append(pred)

    if save_to_db:
        db.session.commit()

    total = len(predictions)
    avg_high_prob = round(sum(p["probabilities"]["High"] for p in predictions) / total, 4) if total > 0 else 0.0

    return {
        "routePlanId": route_plan_id,
        "routePlanName": plan.name,
        "totalEvaluated": total,
        "summary": {
            "lowRiskCount": low_count,
            "mediumRiskCount": med_count,
            "highRiskCount": high_count,
            "highRiskPercentage": round((high_count / total) * 100, 1) if total > 0 else 0.0,
            "avgHighProbability": avg_high_prob,
            "overallRiskLevel": "High" if high_count >= 2 or avg_high_prob >= 0.40 else ("Medium" if (med_count + high_count) > total / 2 else "Low"),
        },
        "predictions": predictions,
        "modelVersion": MODEL_VERSION,
        "modelStatus": MODEL_STATUS,
        "validationStatus": VALIDATION_STATUS,
    }


def list_prediction_history(route_plan_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve saved prediction records from Neon PostgreSQL."""
    query = (
        db.session.query(VisitDelayPrediction, RoutePlan.name)
        .outerjoin(RoutePlan, RoutePlan.id == VisitDelayPrediction.route_plan_id)
        .order_by(VisitDelayPrediction.created_at.desc())
    )

    if route_plan_id:
        query = query.filter(VisitDelayPrediction.route_plan_id == route_plan_id)

    rows = query.limit(min(100, max(1, limit))).all()
    return [rec.to_dict(route_plan_name=plan_name) for rec, plan_name in rows]
