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


class VisitDelayPrediction(db.Model):
    __tablename__ = "visit_delay_predictions"

    id = db.Column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route_plan_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("route_plans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    distributor_id = db.Column(
        UUID(as_uuid=False),
        db.ForeignKey("distributors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    distributor_name = db.Column(db.String(180), nullable=False)
    stop_order = db.Column(db.Integer, nullable=True)
    distance_km = db.Column(db.Float, nullable=True)
    distance_category = db.Column(db.String(20), nullable=False)
    visit_duration_minutes = db.Column(db.Integer, nullable=True)
    visit_duration_category = db.Column(db.String(20), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    priority_category = db.Column(db.String(20), nullable=False)
    probability_low = db.Column(db.Float, nullable=False)
    probability_medium = db.Column(db.Float, nullable=False)
    probability_high = db.Column(db.Float, nullable=False)
    predicted_risk = db.Column(db.String(20), nullable=False)
    recommended_buffer_minutes = db.Column(db.Integer, nullable=False, default=0)
    recommendation_note = db.Column(db.Text, nullable=True)
    model_version = db.Column(db.String(40), nullable=False, default="1.0.0-illustrative")
    model_status = db.Column(db.String(40), nullable=False, default="illustrative_baseline")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def to_dict(self, route_plan_name: str | None = None) -> dict:
        data = {
            "id": str(self.id),
            "routePlanId": str(self.route_plan_id) if self.route_plan_id else None,
            "distributorId": str(self.distributor_id) if self.distributor_id else None,
            "distributorName": self.distributor_name,
            "stopOrder": self.stop_order,
            "distanceKm": float(self.distance_km) if self.distance_km is not None else None,
            "distanceCategory": self.distance_category,
            "visitDurationMinutes": self.visit_duration_minutes,
            "visitDurationCategory": self.visit_duration_category,
            "timeSlot": self.time_slot,
            "priorityCategory": self.priority_category,
            "probabilities": {
                "Low": float(self.probability_low),
                "Medium": float(self.probability_medium),
                "High": float(self.probability_high),
            },
            "predictedRisk": self.predicted_risk,
            "recommendedBufferMinutes": self.recommended_buffer_minutes,
            "recommendation": self.recommendation_note,
            "modelVersion": self.model_version,
            "modelStatus": self.model_status,
            "createdAt": _iso(self.created_at),
        }
        if route_plan_name is not None:
            data["routePlanName"] = route_plan_name
        return data
