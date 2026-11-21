from __future__ import annotations

from datetime import datetime
import re
import uuid

from app.extensions import db
from app.models.types import PortableUUID

_HHMM_RE = re.compile(r"^(\d{2}:\d{2})$")


def format_clock_from_iso(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        stripped = val.strip()
        if _HHMM_RE.match(stripped):
            return stripped
        try:
            dt = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            return f"{dt.hour:02d}:{dt.minute:02d}"
        except ValueError:
            return None
    if isinstance(val, datetime):
        return f"{val.hour:02d}:{val.minute:02d}"
    return None


def _iso(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


class RouteStop(db.Model):
    __tablename__ = "route_stops"

    id = db.Column(
        PortableUUID, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route_plan_id = db.Column(
        PortableUUID,
        db.ForeignKey("route_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_id = db.Column(
        PortableUUID,
        db.ForeignKey("distributors.id", ondelete="SET NULL"),
        nullable=True,
    )
    stop_order = db.Column(db.Integer, nullable=False)
    stop_name = db.Column(db.String(180), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    estimated_arrival = db.Column(db.DateTime(timezone=True), nullable=True)
    estimated_departure = db.Column(db.DateTime(timezone=True), nullable=True)
    travel_from_previous_minutes = db.Column(db.Integer, nullable=True)
    static_travel_from_previous_minutes = db.Column(db.Integer, nullable=True)
    distance_from_previous_km = db.Column(db.Float, nullable=True)
    visit_duration_minutes = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="pending")

    distributor = db.relationship("Distributor", lazy="joined")

    def to_dict(self) -> dict:
        dist_id = str(self.distributor_id) if self.distributor_id else None
        stop_type = (
            "distributor"
            if dist_id is not None
            else ("office_start" if self.stop_order == 1 else "office_end")
        )
        return {
            "id": str(self.id),
            "route_plan_id": str(self.route_plan_id),
            "distributor_id": dist_id,
            "stop_order": int(self.stop_order),
            "stop_name": self.stop_name,
            "stop_type": stop_type,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "estimated_arrival": _iso(self.estimated_arrival),
            "estimated_departure": _iso(self.estimated_departure),
            "estimated_arrival_hhmm": format_clock_from_iso(self.estimated_arrival),
            "estimated_departure_hhmm": format_clock_from_iso(self.estimated_departure),
            "travel_from_previous_minutes": (
                int(self.travel_from_previous_minutes)
                if self.travel_from_previous_minutes is not None
                else None
            ),
            "static_travel_from_previous_minutes": (
                int(self.static_travel_from_previous_minutes)
                if self.static_travel_from_previous_minutes is not None
                else None
            ),
            "distance_from_previous_km": (
                float(self.distance_from_previous_km)
                if self.distance_from_previous_km is not None
                else None
            ),
            "visit_duration_minutes": int(self.visit_duration_minutes or 0),
            "status": self.status,
            "distributor_address": self.distributor.address if self.distributor else None,
            "distributor_priority": (
                int(self.distributor.priority) if self.distributor else None
            ),
        }
