import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, JSON, TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent UUID column.

    Renders as native PostgreSQL UUID in production; falls back to CHAR(36)
    on other backends (e.g. SQLite in tests) so the same models are testable
    without a running PostgreSQL server.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(str(value)))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value))
        return value


# JSON that renders as JSONB on PostgreSQL and plain JSON elsewhere.
JSONType = JSON().with_variant(JSONB, "postgresql")
