from __future__ import annotations

from datetime import datetime, timezone
from flask import Blueprint, request
from pydantic import ValidationError

from app.extensions import db
from app.models import OfficeLocation
from app.routes.common import pydantic_error_response, require_database
from app.utils.responses import fail, ok
from app.utils.validation import OfficeInput, is_valid_uuid

office_bp = Blueprint("office", __name__)


@office_bp.get("/office")
@require_database
def get_offices():
    try:
        rows = (
            db.session.query(OfficeLocation)
            .order_by(OfficeLocation.is_default.desc(), OfficeLocation.created_at.asc())
            .all()
        )
        offices = [r.to_dict() for r in rows]
        return ok({"offices": offices, "defaultOffice": offices[0] if offices else None})
    except Exception:
        return fail(500, "DB_ERROR", "Failed to fetch office locations.")


@office_bp.post("/office")
@require_database
def create_office():
    try:
        data = OfficeInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        if data.is_default:
            db.session.query(OfficeLocation).update({OfficeLocation.is_default: False})
        office = OfficeLocation(
            name=data.name,
            address=data.address,
            latitude=data.latitude,
            longitude=data.longitude,
            is_default=data.is_default,
        )
        db.session.add(office)
        db.session.commit()
        return ok(office.to_dict(), "Office location created", 201)
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to create office location.")


@office_bp.put("/office/<office_id>")
@require_database
def update_office(office_id: str):
    if not is_valid_uuid(office_id):
        return fail(400, "INVALID_ID", "Invalid office ID format.")

    try:
        data = OfficeInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        office = db.session.get(OfficeLocation, office_id)
        if office is None:
            return fail(404, "NOT_FOUND", "Office location not found.")

        if data.is_default:
            db.session.query(OfficeLocation).filter(OfficeLocation.id != office_id).update(
                {OfficeLocation.is_default: False}
            )

        office.name = data.name
        office.address = data.address
        office.latitude = data.latitude
        office.longitude = data.longitude
        office.is_default = data.is_default
        office.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return ok(office.to_dict(), "Office location updated")
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to update office location.")
