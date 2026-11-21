from __future__ import annotations

from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.extensions import db


class DistributorCluster(db.Model):
    __tablename__ = "distributor_clusters"

    id = db.Column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route_plan_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("route_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    cluster_number = db.Column(db.Integer, nullable=False)
    cluster_label = db.Column(db.String(100), nullable=True)
    centroid_latitude = db.Column(db.Float, nullable=True)
    centroid_longitude = db.Column(db.Float, nullable=True)
    distributor_ids = db.Column(
        ARRAY(UUID(as_uuid=False)), nullable=False, default=list
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
