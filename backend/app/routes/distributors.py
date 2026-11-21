from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
from flask import Blueprint, Response, request
from pydantic import ValidationError
from sqlalchemy import or_

from app.extensions import db
from app.models import Distributor
from app.routes.common import pydantic_error_response, require_database
from app.utils.responses import fail, ok
from app.utils.validation import DistributorInput, is_valid_uuid

distributors_bp = Blueprint("distributors", __name__)


def _sanitize_csv_cell(value: str | None) -> str:
    text_val = value or ""
    if text_val and text_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text_val}"
    return text_val


@distributors_bp.get("/distributors/export")
@require_database
def export_distributors():
    try:
        rows = (
            db.session.query(Distributor)
            .order_by(Distributor.priority.desc(), Distributor.name.asc())
            .all()
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "name",
                "contact_person",
                "phone",
                "email",
                "address",
                "latitude",
                "longitude",
                "priority",
                "visit_duration_minutes",
                "opening_time",
                "closing_time",
                "is_active",
                "notes",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    _sanitize_csv_cell(r.name),
                    _sanitize_csv_cell(r.contact_person),
                    _sanitize_csv_cell(r.phone),
                    _sanitize_csv_cell(r.email),
                    _sanitize_csv_cell(r.address),
                    r.latitude,
                    r.longitude,
                    r.priority,
                    r.visit_duration_minutes,
                    r.opening_time,
                    r.closing_time,
                    "true" if r.is_active else "false",
                    _sanitize_csv_cell(r.notes),
                ]
            )
        return Response(
            output.getvalue(),
            status=200,
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": 'attachment; filename="distributors.csv"',
            },
        )
    except Exception:
        return fail(500, "EXPORT_FAILED", "Failed to export distributors CSV.")


@distributors_bp.post("/distributors/import")
@require_database
def import_distributors():
    body = request.get_json(silent=True) or {}
    csv_text = body.get("csv") if isinstance(body.get("csv"), str) else ""
    if not csv_text.strip():
        return fail(400, "VALIDATION_ERROR", "CSV content is empty.")
    if len(csv_text.encode("utf-8")) > 256 * 1024:
        return fail(400, "VALIDATION_ERROR", "CSV payload exceeds 256 KB size limit.")

    lines = [line.strip() for line in csv_text.splitlines() if line.strip()]
    if len(lines) < 2:
        return fail(
            400,
            "VALIDATION_ERROR",
            "CSV must include a header row and at least one data row.",
        )
    if len(lines) - 1 > 200:
        return fail(
            400,
            "VALIDATION_ERROR",
            "CSV import is capped at 200 rows per request.",
        )

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if not reader.fieldnames:
        return fail(400, "VALIDATION_ERROR", "CSV header row is missing.")

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    required_cols = [
        "name",
        "contact_person",
        "phone",
        "address",
        "latitude",
        "longitude",
    ]
    for col in required_cols:
        if col not in normalized_headers:
            return fail(400, "VALIDATION_ERROR", f"Missing required CSV column: {col}")

    valid_rows: list[DistributorInput] = []
    errors: list[dict] = []

    for idx, raw_row in enumerate(reader, start=2):
        def get_val(col_name: str, default: str = "") -> str:
            orig_key = normalized_headers.get(col_name)
            if not orig_key:
                return default
            val = raw_row.get(orig_key)
            return val.strip() if isinstance(val, str) and val.strip() else default

        try:
            lat = float(get_val("latitude", "nan"))
            lng = float(get_val("longitude", "nan"))
            prio_str = get_val("priority")
            dur_str = get_val("visit_duration_minutes")
            active_str = get_val("is_active")
            candidate = DistributorInput.model_validate(
                {
                    "name": get_val("name"),
                    "contact_person": get_val("contact_person"),
                    "phone": get_val("phone"),
                    "email": get_val("email"),
                    "address": get_val("address"),
                    "latitude": lat,
                    "longitude": lng,
                    "priority": int(prio_str) if prio_str else 3,
                    "visit_duration_minutes": int(dur_str) if dur_str else 30,
                    "opening_time": get_val("opening_time", "08:00"),
                    "closing_time": get_val("closing_time", "18:00"),
                    "is_active": active_str.lower() != "false" if active_str else True,
                    "notes": get_val("notes", ""),
                }
            )
            valid_rows.append(candidate)
        except (ValueError, ValidationError) as exc:
            msg = (
                exc.errors()[0].get("msg", "Invalid row")
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            errors.append({"row": idx, "message": msg})

    if errors:
        return fail(
            400,
            "CSV_VALIDATION_ERROR",
            f"CSV contains {len(errors)} invalid row(s).",
            errors[:10],
        )

    try:
        created: list[dict] = []
        for d in valid_rows:
            row = Distributor(
                name=d.name,
                contact_person=d.contact_person,
                phone=d.phone,
                email=d.email or None,
                address=d.address,
                latitude=d.latitude,
                longitude=d.longitude,
                priority=d.priority,
                visit_duration_minutes=d.visit_duration_minutes,
                opening_time=d.opening_time,
                closing_time=d.closing_time,
                is_active=d.is_active,
                notes=d.notes,
            )
            db.session.add(row)
            db.session.flush()
            created.append(row.to_dict())
        db.session.commit()
        return ok(
            {"importedCount": len(created), "items": created},
            f"Imported {len(created)} distributor(s).",
            201,
        )
    except Exception:
        db.session.rollback()
        return fail(
            500, "IMPORT_FAILED", "Failed to import distributors into database."
        )


@distributors_bp.get("/distributors")
@require_database
def list_distributors():
    try:
        search = (request.args.get("search") or "").strip()
        active = request.args.get("active") or "all"
        sort_by = request.args.get("sortBy") or "priority"
        sort_dir = "asc" if request.args.get("sortDir") == "asc" else "desc"
        try:
            page = max(1, int(request.args.get("page") or 1))
            page_size = min(100, max(1, int(request.args.get("pageSize") or 50)))
        except ValueError:
            return fail(400, "VALIDATION_ERROR", "page and pageSize must be integers.")

        query_obj = db.session.query(Distributor)
        if search:
            pattern = f"%{search}%"
            query_obj = query_obj.filter(
                or_(
                    Distributor.name.ilike(pattern),
                    Distributor.contact_person.ilike(pattern),
                    Distributor.address.ilike(pattern),
                )
            )
        if active == "true":
            query_obj = query_obj.filter(Distributor.is_active.is_(True))
        elif active == "false":
            query_obj = query_obj.filter(Distributor.is_active.is_(False))

        sort_map = {
            "name": Distributor.name,
            "priority": Distributor.priority,
            "visit_duration_minutes": Distributor.visit_duration_minutes,
            "created_at": Distributor.created_at,
        }
        col = sort_map.get(sort_by, Distributor.priority)
        order_expr = col.asc() if sort_dir == "asc" else col.desc()

        total = query_obj.count()
        offset = (page - 1) * page_size
        rows = (
            query_obj.order_by(order_expr, Distributor.name.asc())
            .limit(page_size)
            .offset(offset)
            .all()
        )

        return ok(
            {
                "items": [r.to_dict() for r in rows],
                "pagination": {
                    "page": page,
                    "pageSize": page_size,
                    "total": total,
                    "totalPages": max(1, (total + page_size - 1) // page_size),
                },
            }
        )
    except Exception:
        return fail(500, "DB_ERROR", "Failed to list distributors.")


@distributors_bp.post("/distributors")
@require_database
def create_distributor():
    try:
        d = DistributorInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        row = Distributor(
            name=d.name,
            contact_person=d.contact_person,
            phone=d.phone,
            email=d.email or None,
            address=d.address,
            latitude=d.latitude,
            longitude=d.longitude,
            priority=d.priority,
            visit_duration_minutes=d.visit_duration_minutes,
            opening_time=d.opening_time,
            closing_time=d.closing_time,
            is_active=d.is_active,
            notes=d.notes,
        )
        db.session.add(row)
        db.session.commit()
        return ok(row.to_dict(), "Distributor created", 201)
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to create distributor.")


@distributors_bp.get("/distributors/<dist_id>")
@require_database
def get_distributor(dist_id: str):
    if not is_valid_uuid(dist_id):
        return fail(400, "INVALID_ID", "Invalid distributor ID format.")
    try:
        row = db.session.get(Distributor, dist_id)
        if row is None:
            return fail(404, "NOT_FOUND", "Distributor not found.")
        return ok(row.to_dict())
    except Exception:
        return fail(500, "DB_ERROR", "Failed to load distributor.")


@distributors_bp.put("/distributors/<dist_id>")
@require_database
def update_distributor(dist_id: str):
    if not is_valid_uuid(dist_id):
        return fail(400, "INVALID_ID", "Invalid distributor ID format.")

    try:
        d = DistributorInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return pydantic_error_response(exc)

    try:
        row = db.session.get(Distributor, dist_id)
        if row is None:
            return fail(404, "NOT_FOUND", "Distributor not found.")
        row.name = d.name
        row.contact_person = d.contact_person
        row.phone = d.phone
        row.email = d.email or None
        row.address = d.address
        row.latitude = d.latitude
        row.longitude = d.longitude
        row.priority = d.priority
        row.visit_duration_minutes = d.visit_duration_minutes
        row.opening_time = d.opening_time
        row.closing_time = d.closing_time
        row.is_active = d.is_active
        row.notes = d.notes
        row.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return ok(row.to_dict(), "Distributor updated")
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to update distributor.")


@distributors_bp.delete("/distributors/<dist_id>")
@require_database
def delete_distributor(dist_id: str):
    if not is_valid_uuid(dist_id):
        return fail(400, "INVALID_ID", "Invalid distributor ID format.")
    try:
        row = db.session.get(Distributor, dist_id)
        if row is None:
            return fail(404, "NOT_FOUND", "Distributor not found.")
        db.session.delete(row)
        db.session.commit()
        return ok({"id": dist_id}, "Distributor deleted")
    except Exception:
        db.session.rollback()
        return fail(500, "DB_ERROR", "Failed to delete distributor.")
