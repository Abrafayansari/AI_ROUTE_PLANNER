from __future__ import annotations

import functools
import time
from flask import request

from app.services import is_database_configured
from app.utils.responses import fail


def require_database(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_database_configured():
            return fail(
                503,
                "DATABASE_NOT_CONFIGURED",
                "Neon PostgreSQL DATABASE_URL is not configured in server-side Secrets.",
            )
        return fn(*args, **kwargs)

    return wrapper


def pydantic_error_response(exc):
    errors = exc.errors() if hasattr(exc, "errors") else []
    first_msg = errors[0].get("msg", "Invalid input") if errors else "Invalid input"
    if first_msg.startswith("Value error, "):
        first_msg = first_msg[len("Value error, ") :]
    return fail(400, "VALIDATION_ERROR", first_msg, errors)


def rate_limit(max_requests: int = 60, window_seconds: float = 60.0):
    hits: dict[str, list[float]] = {}

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = request.remote_addr or "local"
            now = time.monotonic()
            recent = [ts for ts in hits.get(key, []) if now - ts < window_seconds]
            if len(recent) >= max_requests:
                return fail(
                    429,
                    "RATE_LIMIT_EXCEEDED",
                    "Too many optimization requests. Please wait a moment and try again.",
                )
            recent.append(now)
            hits[key] = recent
            return fn(*args, **kwargs)

        return wrapper

    return decorator
