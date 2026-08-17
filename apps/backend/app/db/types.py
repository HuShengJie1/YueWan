from datetime import UTC, datetime

from sqlalchemy import DateTime, Uuid
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

UUID_COLUMN_TYPE = Uuid(as_uuid=True, native_uuid=False)

MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC as MySQL DATETIME(6) and expose timezone-aware values."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "mysql":
            return dialect.type_descriptor(DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("database datetimes must include a timezone")
        normalized = value.astimezone(UTC)
        if dialect.name == "mysql":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, _dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
