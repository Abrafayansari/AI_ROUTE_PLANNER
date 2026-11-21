from __future__ import annotations

import os
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()

_DB_URL_SECRET_RE = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s'\"]+", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    """Strip any PostgreSQL connection strings from logs or error messages."""
    return _DB_URL_SECRET_RE.sub("[REDACTED_DATABASE_URL]", str(text or ""))


def normalize_sqlalchemy_database_url(raw_url: str | None) -> str | None:
    """Normalize Neon PostgreSQL URL for SQLAlchemy + psycopg v3."""
    if not raw_url:
        return None
    cleaned = raw_url.strip()
    if not cleaned:
        return None

    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgres://") :]
    elif cleaned.startswith("postgresql://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    elif cleaned.startswith("postgresql+psycopg2://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgresql+psycopg2://") :]

    # Preserve SSL parameters while safely handling channel_binding if needed
    parsed = urlparse(cleaned)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    # Keep sslmode=require if specified; drop channel_binding only if empty or unsupported
    filtered_pairs = [(k, v) for (k, v) in query_pairs if k.lower() != "channel_binding"]
    if not any(k.lower() == "sslmode" for k, _ in filtered_pairs):
        if "neon.tech" in (parsed.hostname or "").lower():
            filtered_pairs.append(("sslmode", "require"))

    new_query = urlencode(filtered_pairs)
    return urlunparse(parsed._replace(query=new_query))


class Config:
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    PORT: int = int(os.getenv("PORT", "5000"))
    RAW_DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    SQLALCHEMY_DATABASE_URI: str = (
        normalize_sqlalchemy_database_url(RAW_DATABASE_URL) or "sqlite:///:memory:"
    )
    DATABASE_CONFIGURED: bool = bool(RAW_DATABASE_URL and RAW_DATABASE_URL.strip())
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = (
        {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 5,
            "max_overflow": 5,
        }
        if DATABASE_CONFIGURED
        else {}
    )
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_URL",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]
