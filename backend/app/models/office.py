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


class OfficeLocation(db.Model):
    __tablename__ = "office_locations"

    id = db.Column(
        PortableUUID, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = db.Column(db.String(160), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    is_default = db.Column(db.Boolean, nullable=False, default=True)
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
            "address": self.address,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "is_default": bool(self.is_default),
            "is_demo": bool(self.is_demo),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
