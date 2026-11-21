from __future__ import annotations

from datetime import datetime, timezone
import uuid

from app.extensions import db
from app.models.types import PortableUUID


def _iso(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


class Distributor(db.Model):
    __tablename__ = "distributors"

    id = db.Column(
        PortableUUID, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = db.Column(db.String(180), nullable=False)
    contact_person = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(180), nullable=True)
    address = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    priority = db.Column(db.SmallInteger, nullable=False, default=3)
    visit_duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    opening_time = db.Column(db.String(10), nullable=False, default="08:00")
    closing_time = db.Column(db.String(10), nullable=False, default="18:00")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
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

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "priority": int(self.priority),
            "visit_duration_minutes": int(self.visit_duration_minutes),
            "opening_time": self.opening_time,
            "closing_time": self.closing_time,
            "is_active": bool(self.is_active),
            "notes": self.notes or "",
            "is_demo": bool(self.is_demo),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
