from __future__ import annotations

from typing import Any
from flask import jsonify


def ok(data: Any, message: str = "Operation completed", status: int = 200):
    return jsonify({"success": True, "data": data, "message": message}), status


def fail(status: int, code: str, message: str, details: Any = None):
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error_obj["details"] = details
    return jsonify({"success": False, "error": error_obj}), status
