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

    def _client_key() -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            first_ip = forwarded.split(",")[0].strip()
            if first_ip:
                return first_ip
        return request.remote_addr or "local"

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            now = time.monotonic()
            # Prune stale keys periodically to bound memory
            if len(hits) > 512:
                stale_keys = [
                    k for k, ts_list in hits.items()
                    if not any(now - ts < window_seconds for ts in ts_list)
                ]
                for sk in stale_keys:
                    hits.pop(sk, None)

            key = _client_key()
            recent = [ts for ts in hits.get(key, []) if now - ts < window_seconds]
            if len(recent) >= max_requests:
                hits[key] = recent
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
