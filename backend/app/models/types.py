from __future__ import annotations

import json
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.types import Text, TypeDecorator

from app.extensions import db

PortableUUID = db.String(36).with_variant(UUID(as_uuid=False), "postgresql")
PortableJSON = db.JSON().with_variant(JSONB, "postgresql")
PortableBigIntPK = db.BigInteger().with_variant(db.Integer, "sqlite")


class PortableUUIDList(TypeDecorator):
    """Stores UUID[] on PostgreSQL and JSON-encoded string arrays on SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(UUID(as_uuid=False)))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        vals = [str(v) for v in (value or [])]
        if dialect.name == "postgresql":
            return vals
        return json.dumps(vals)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return [str(v) for v in parsed] if isinstance(parsed, list) else []
            except ValueError:
                return []
        return []
