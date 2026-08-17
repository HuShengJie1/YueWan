from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import JSON, PrimaryKeyConstraint, String, UniqueConstraint, Uuid
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401
from app.db.base import Base
from app.db.types import UTCDateTime

EXPECTED_TABLES = {
    "events",
    "group_members",
    "groups",
    "hangouts",
    "proposal_votes",
    "proposals",
    "time_options",
    "time_votes",
    "users",
}


def test_mvp_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_business_tables_use_uuid_primary_keys_and_timestamps() -> None:
    for table in Base.metadata.tables.values():
        assert isinstance(table.c.id.type, Uuid)
        assert table.c.id.type.native_uuid is False
        assert table.c.id.primary_key
        assert table.c.id.default is not None
        assert table.c.id.server_default is None

        for column_name in ("created_at", "updated_at"):
            column = table.c[column_name]
            assert isinstance(column.type, UTCDateTime)
            assert column.default is not None
            assert column.nullable is False
            assert column.server_default is not None


def test_all_business_datetimes_use_utc_adapter() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_at"):
                assert isinstance(column.type, UTCDateTime), (
                    f"{table.name}.{column.name} lacks UTC adapter"
                )


def test_utc_datetime_normalizes_mysql_values() -> None:
    column_type = UTCDateTime()
    mysql_dialect = mysql.dialect()
    china_timezone = timezone(timedelta(hours=8))
    china_time = datetime(2026, 8, 16, 12, 0, tzinfo=china_timezone)

    stored = column_type.process_bind_param(china_time, mysql_dialect)
    assert stored == datetime(2026, 8, 16, 4, 0)
    assert stored.tzinfo is None
    assert column_type.process_result_value(stored, mysql_dialect) == datetime(
        2026, 8, 16, 4, 0, tzinfo=UTC
    )

    with pytest.raises(ValueError, match="must include a timezone"):
        column_type.process_bind_param(datetime(2026, 8, 15, 20, 0), mysql_dialect)


def test_every_foreign_key_has_a_leftmost_index() -> None:
    for table in Base.metadata.tables.values():
        indexed_column_groups = [
            tuple(column.name for column in index.columns) for index in table.indexes
        ]
        indexed_column_groups.extend(
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint))
        )

        for column in table.columns:
            if column.foreign_keys:
                assert any(
                    columns and columns[0] == column.name for columns in indexed_column_groups
                ), f"{table.name}.{column.name} is an unindexed foreign key"


def test_vote_and_membership_uniqueness_constraints() -> None:
    expected_unique_columns = {
        "group_members": ("group_id", "user_id"),
        "proposal_votes": ("proposal_id", "user_id"),
        "time_votes": ("time_option_id", "user_id"),
        "events": ("hangout_id",),
    }

    for table_name, expected_columns in expected_unique_columns.items():
        constraints = Base.metadata.tables[table_name].constraints
        unique_column_groups = {
            tuple(column.name for column in constraint.columns)
            for constraint in constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert expected_columns in unique_column_groups


def test_persisted_enum_values_match_product_contract() -> None:
    assert Base.metadata.tables["group_members"].c.role.type.enums == ["owner", "member"]
    assert Base.metadata.tables["group_members"].c.status.type.enums == ["active", "left"]
    assert Base.metadata.tables["hangouts"].c.status.type.enums == [
        "draft",
        "voting",
        "confirmed",
        "cancelled",
        "finished",
    ]
    assert Base.metadata.tables["proposal_votes"].c.value.type.enums == [
        "LIKE",
        "OK",
        "DISLIKE",
    ]


def test_user_authentication_fields_are_registered() -> None:
    users = Base.metadata.tables["users"]

    assert users.c.is_active.nullable is False
    assert users.c.is_active.server_default is not None
    assert users.c.profile_completed.nullable is False
    assert users.c.profile_completed.server_default is not None
    assert isinstance(users.c.last_login_at.type, UTCDateTime)
    assert isinstance(users.c.wechat_openid.type, String)
    assert users.c.wechat_openid.type.length == 128
    assert users.c.wechat_openid.type.collation == "utf8mb4_0900_bin"


def test_mysql_schema_uses_portable_types_and_table_options() -> None:
    proposals = Base.metadata.tables["proposals"]
    assert isinstance(proposals.c.external_data.type, JSON)

    for table in Base.metadata.tables.values():
        assert table.dialect_options["mysql"]["engine"] == "InnoDB"
        assert table.dialect_options["mysql"]["charset"] == "utf8mb4"
        assert table.dialect_options["mysql"]["collate"] == "utf8mb4_0900_ai_ci"

        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert "JSONB" not in ddl
        assert "btrim(" not in ddl


def test_hangout_cross_status_list_index_matches_keyset_order() -> None:
    hangouts = Base.metadata.tables["hangouts"]
    index_columns = {tuple(column.name for column in index.columns) for index in hangouts.indexes}

    assert ("group_id", "created_at", "id") in index_columns


def test_candidate_list_indexes_match_keyset_orders() -> None:
    proposals = Base.metadata.tables["proposals"]
    proposal_indexes = {
        tuple(column.name for column in index.columns) for index in proposals.indexes
    }
    time_options = Base.metadata.tables["time_options"]
    time_option_indexes = {
        tuple(column.name for column in index.columns) for index in time_options.indexes
    }

    assert ("hangout_id", "created_at", "id") in proposal_indexes
    assert ("hangout_id", "starts_at", "id") in time_option_indexes
