from __future__ import annotations

from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


def _iso(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


class ScheduleEntry(db.Model):
    __tablename__ = "schedule_entries"

    id = db.Column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route_plan_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("route_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("distributors.id", ondelete="SET NULL"),
        nullable=True,
    )
    distributor_name = db.Column(db.String(180), nullable=False)
    scheduled_start = db.Column(db.DateTime(timezone=True), nullable=False)
    scheduled_end = db.Column(db.DateTime(timezone=True), nullable=False)
    visit_duration_minutes = db.Column(db.Integer, nullable=False)
    priority = db.Column(db.SmallInteger, nullable=False, default=3)
    cluster_number = db.Column(db.Integer, nullable=True)
    is_feasible = db.Column(db.Boolean, nullable=False, default=True)
    constraint_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    distributor = db.relationship("Distributor", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "route_plan_id": str(self.route_plan_id),
            "distributor_id": str(self.distributor_id) if self.distributor_id else None,
            "distributor_name": self.distributor_name,
            "scheduled_start": _iso(self.scheduled_start),
            "scheduled_end": _iso(self.scheduled_end),
            "visit_duration_minutes": int(self.visit_duration_minutes),
            "priority": int(self.priority),
            "cluster_number": self.cluster_number,
            "is_feasible": bool(self.is_feasible),
            "constraint_notes": self.constraint_notes or "",
            "created_at": _iso(self.created_at),
        }
