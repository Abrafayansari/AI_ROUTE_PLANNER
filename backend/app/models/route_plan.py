from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


def _iso(val: datetime | date | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val)


class FieldOfficer(db.Model):
    __tablename__ = "field_officers"

    id = db.Column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = db.Column(db.String(140), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    territory = db.Column(db.String(140), nullable=True)
    work_start_time = db.Column(db.String(10), nullable=False, default="09:00")
    work_end_time = db.Column(db.String(10), nullable=False, default="17:00")
    max_daily_visits = db.Column(db.Integer, nullable=False, default=10)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RoutePlan(db.Model):
    __tablename__ = "route_plans"

    id = db.Column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = db.Column(db.String(180), nullable=False)
    plan_date = db.Column(db.Date, nullable=False)
    officer_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("field_officers.id", ondelete="SET NULL"),
        nullable=True,
    )
    office_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("office_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    travel_mode = db.Column(db.String(40), nullable=False, default="simulated_vehicle")
    return_to_office = db.Column(db.Boolean, nullable=False, default=True)
    recommended_algorithm = db.Column(db.String(50), nullable=True)
    selected_algorithm = db.Column(db.String(50), nullable=True)
    total_distance_km = db.Column(db.Float, nullable=False, default=0.0)
    total_duration_minutes = db.Column(db.Integer, nullable=False, default=0)
    distance_multiplier = db.Column(db.Float, nullable=False, default=1.25)
    graph_seed = db.Column(db.Integer, nullable=False, default=42)
    status = db.Column(db.String(30), nullable=False, default="draft")
    map_provider = db.Column(db.String(40), nullable=False, default="simulated")
    notes = db.Column(db.Text, nullable=False, default="")
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    office = db.relationship("OfficeLocation", lazy="joined")

    def to_dict(
        self,
        stop_count: int | None = None,
        visited_count: int | None = None,
        include_office_address: bool = False,
    ) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "plan_date": _iso(self.plan_date),
            "officer_id": str(self.officer_id) if self.officer_id else None,
            "office_id": str(self.office_id),
            "office_name": self.office.name if self.office else None,
            "office_latitude": float(self.office.latitude) if self.office else None,
            "office_longitude": float(self.office.longitude) if self.office else None,
            "travel_mode": self.travel_mode,
            "return_to_office": bool(self.return_to_office),
            "recommended_algorithm": self.recommended_algorithm,
            "selected_algorithm": self.selected_algorithm,
            "total_distance_km": float(self.total_distance_km or 0.0),
            "total_duration_minutes": int(round(float(self.total_duration_minutes or 0))),
            "distance_multiplier": float(self.distance_multiplier or 1.25),
            "graph_seed": int(self.graph_seed or 42),
            "status": self.status,
            "map_provider": self.map_provider,
            "notes": self.notes or "",
            "is_demo": bool(self.is_demo),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
        if include_office_address and self.office:
            data["office_address"] = self.office.address
        if stop_count is not None:
            data["stop_count"] = int(stop_count)
        if visited_count is not None:
            data["visited_count"] = int(visited_count)
        return data


class ApiRequestLog(db.Model):
    __tablename__ = "api_request_logs"

    id = db.Column(db.BigInteger, primary_key=True)
    provider = db.Column(db.String(60), nullable=False)
    endpoint = db.Column(db.String(160), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    success = db.Column(db.Boolean, nullable=False, default=False)
    duration_ms = db.Column(db.Float, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
