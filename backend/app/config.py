from __future__ import annotations

import os
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()

_DB_URL_SECRET_RE = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s'\"]+", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    """Strip PostgreSQL URLs and API keys from logs or error messages."""
    cleaned = _DB_URL_SECRET_RE.sub("[REDACTED_DATABASE_URL]", str(text or ""))
    for env_name, placeholder in (
        ("GOOGLE_MAPS_API_KEY", "[REDACTED_GOOGLE_MAPS_API_KEY]"),
        ("OPENROUTESERVICE_API_KEY", "[REDACTED_OPENROUTESERVICE_API_KEY]"),
    ):
        secret_val = os.getenv(env_name, "").strip()
        if secret_val and secret_val in cleaned:
            cleaned = cleaned.replace(secret_val, placeholder)
    return cleaned


def is_postgresql_uri(uri: str | None) -> bool:
    return bool(uri and uri.strip().lower().startswith("postgresql"))


def is_placeholder_database_url(raw_url: str | None) -> bool:
    """Detect unset or template-placeholder DATABASE_URL values."""
    if not raw_url or not raw_url.strip():
        return True
    cleaned = raw_url.strip()
    if cleaned.lower().startswith("sqlite:"):
        return False
    if any(marker in cleaned for marker in ("<", ">", "USER:PASSWORD", "YOUR_", "placeholder")):
        return True
    try:
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").strip().lower()
    except Exception:
        return True
    return host in {"", "host", "your-host", "your_host", "db_host", "placeholder", "example.com"}


def is_placeholder_api_key(raw_key: str | None) -> bool:
    """Detect unset or placeholder external API keys."""
    if not raw_key or not str(raw_key).strip():
        return True
    cleaned = str(raw_key).strip()
    if any(marker in cleaned for marker in ("<", ">", "YOUR_", "YOUR-KEY", "placeholder", "AIzaSyDummy", "sample_key")):
        return True
    return False


def get_local_sqlite_database_url() -> str:
    """Return a writable local SQLite URI under backend/instance for zero-config runtime fallback."""
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance_dir = os.path.join(backend_dir, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.path.join(instance_dir, "smart_route_planner.db").replace("\\", "/")
    return f"sqlite:///{db_path}"


def normalize_sqlalchemy_database_url(raw_url: str | None) -> str | None:
    """Normalize Neon PostgreSQL URL for SQLAlchemy + psycopg v3 while preserving SQLite URIs."""
    if not raw_url:
        return None
    cleaned = raw_url.strip()
    if not cleaned:
        return None

    if cleaned.lower().startswith("sqlite:"):
        # Handle SQLite relative/absolute paths robustly on Windows and cross-platform
        # e.g., sqlite:///backend/instance/smart_route_planner.db
        prefix = "sqlite:///"
        if cleaned.lower().startswith(prefix):
            raw_path = cleaned[len(prefix):]
            # If it's a relative path, resolve relative to project root or backend dir
            if not os.path.isabs(raw_path) and not (len(raw_path) > 1 and raw_path[1] == ":"):
                # Resolve relative to root
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                abs_path = os.path.abspath(os.path.join(project_root, raw_path))
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                return f"sqlite:///{abs_path.replace(os.sep, '/')}"
        return cleaned

    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgres://") :]
    elif cleaned.startswith("postgresql://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    elif cleaned.startswith("postgresql+psycopg2://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgresql+psycopg2://") :]

    # Preserve SSL parameters while safely handling channel_binding if needed
    parsed = urlparse(cleaned)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    # Keep sslmode=require if specified; drop channel_binding only if unsupported
    filtered_pairs = [(k, v) for (k, v) in query_pairs if k.lower() != "channel_binding"]
    hostname = (parsed.hostname or "").lower()
    if not any(k.lower() == "sslmode" for k, _ in filtered_pairs):
        if hostname not in ("localhost", "127.0.0.1", "::1"):
            filtered_pairs.append(("sslmode", "require"))

    new_query = urlencode(filtered_pairs)
    return urlunparse(parsed._replace(query=new_query))


def build_engine_options(uri: str | None, configured: bool) -> dict:
    if configured and is_postgresql_uri(uri):
        return {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 5,
            "max_overflow": 5,
            "connect_args": {"connect_timeout": 3},
        }
    return {}


class Config:
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    PORT: int = int(os.getenv("PORT", "5000"))
    RAW_DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    SQLALCHEMY_DATABASE_URI: str = (
        normalize_sqlalchemy_database_url(RAW_DATABASE_URL) or "sqlite:///:memory:"
    )
    DATABASE_CONFIGURED: bool = bool(RAW_DATABASE_URL and RAW_DATABASE_URL.strip())
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = build_engine_options(
        SQLALCHEMY_DATABASE_URI, DATABASE_CONFIGURED
    )
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    OSRM_BASE_URL: str = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").strip().rstrip("/")
    OSRM_PROFILE: str = os.getenv("OSRM_PROFILE", "driving").strip() or "driving"
    OPENROUTESERVICE_API_KEY: str = os.getenv("OPENROUTESERVICE_API_KEY", "").strip()
    OPENROUTESERVICE_BASE_URL: str = (
        os.getenv("OPENROUTESERVICE_BASE_URL", "https://api.openrouteservice.org").strip().rstrip("/")
    )
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_URL",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]