from __future__ import annotations

from datetime import datetime, timezone
import uuid

from app.extensions import db
from app.models.types import PortableJSON, PortableUUID, PortableUUIDList


def _iso(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


class AlgorithmRun(db.Model):
    __tablename__ = "algorithm_runs"

    id = db.Column(
        PortableUUID, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route_plan_id = db.Column(
        PortableUUID,
        db.ForeignKey("route_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    algorithm_name = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="completed")
    route_order = db.Column(PortableUUIDList, nullable=False, default=list)
    route_names = db.Column(PortableJSON, nullable=False, default=list)
    total_cost = db.Column(db.Float, nullable=True)
    total_distance_km = db.Column(db.Float, nullable=True)
    estimated_duration_minutes = db.Column(db.Integer, nullable=True)
    nodes_expanded = db.Column(db.Integer, nullable=True)
    execution_time_ms = db.Column(db.Float, nullable=True)
    parameters = db.Column(PortableJSON, nullable=False, default=dict)
    result_details = db.Column(PortableJSON, nullable=False, default=dict)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self, route_plan_name: str | None = None) -> dict:
        data = {
            "id": str(self.id),
            "route_plan_id": str(self.route_plan_id),
            "algorithm_name": self.algorithm_name,
            "status": self.status,
            "route_order": [str(x) for x in (self.route_order or [])],
            "route_names": self.route_names or [],
            "total_cost": float(self.total_cost) if self.total_cost is not None else 0.0,
            "total_distance_km": (
                float(self.total_distance_km)
                if self.total_distance_km is not None
                else 0.0
            ),
            "estimated_duration_minutes": (
                int(self.estimated_duration_minutes)
                if self.estimated_duration_minutes is not None
                else 0
            ),
            "nodes_expanded": int(self.nodes_expanded or 0),
            "execution_time_ms": (
                float(self.execution_time_ms)
                if self.execution_time_ms is not None
                else 0.0
            ),
            "parameters": self.parameters or {},
            "result_details": self.result_details or {},
            "error_message": self.error_message,
            "created_at": _iso(self.created_at),
        }
        if route_plan_name is not None:
            data["route_plan_name"] = route_plan_name
        return data
