from __future__ import annotations

from datetime import datetime, timezone
from flask import Blueprint, request
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import OfficeLocation, RoutePlan
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


@office_bp.delete("/office/<office_id>")
@require_database
def delete_office(office_id: str):
    if not is_valid_uuid(office_id):
        return fail(400, "INVALID_ID", "Invalid office ID format.")

    try:
        office = db.session.get(OfficeLocation, office_id)
        if office is None:
            return fail(404, "NOT_FOUND", "Office location not found.")

        non_workspace_plans = (
            db.session.query(RoutePlan)
            .filter(
                RoutePlan.office_id == office_id,
                ~or_(
                    RoutePlan.name == "K-Means Clustering Workspace",
                    RoutePlan.name.like("CSP Schedule — %"),
                ),
            )
            .count()
        )
        if non_workspace_plans > 0:
            return fail(
                409,
                "OFFICE_IN_USE",
                f"Cannot delete office '{office.name}' because it is referenced by {non_workspace_plans} saved route plan(s).",
            )

        # Reassign or clean up any workspace route plans attached to this office
        workspace_plans = (
            db.session.query(RoutePlan)
            .filter(
                RoutePlan.office_id == office_id,
                or_(
                    RoutePlan.name == "K-Means Clustering Workspace",
                    RoutePlan.name.like("CSP Schedule — %"),
                ),
            )
            .all()
        )
        if workspace_plans:
            fallback_office = (
                db.session.query(OfficeLocation)
                .filter(OfficeLocation.id != office_id)
                .order_by(OfficeLocation.is_default.desc(), OfficeLocation.created_at.asc())
                .first()
            )
            if fallback_office is not None:
                for wp in workspace_plans:
                    wp.office_id = str(fallback_office.id)
                db.session.flush()
            else:
                return fail(
                    409,
                    "OFFICE_IN_USE",
                    "Cannot delete the only remaining office while active clustering/scheduling workspace records exist.",
                )

        was_default = bool(office.is_default)
        db.session.delete(office)
        db.session.flush()

        if was_default:
            next_default = (
                db.session.query(OfficeLocation)
                .order_by(OfficeLocation.created_at.asc())
                .first()
            )
            if next_default is not None:
                next_default.is_default = True

        db.session.commit()
        return ok({"id": office_id}, "Office location deleted")
    except IntegrityError:
        db.session.rollback()
        return fail(
            409,
            "OFFICE_IN_USE",
            "Cannot delete this office because existing route plans depend on it.",
        )
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to delete office location.")
