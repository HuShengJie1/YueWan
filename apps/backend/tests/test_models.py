from sqlalchemy import DateTime, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID

import app.models  # noqa: F401
from app.db.base import Base

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
        assert isinstance(table.c.id.type, PGUUID)
        assert table.c.id.primary_key
        assert table.c.id.default is not None
        assert table.c.id.server_default is None

        for column_name in ("created_at", "updated_at"):
            column = table.c[column_name]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone is True
            assert column.nullable is False
            assert column.server_default is not None


def test_all_business_datetimes_are_timezone_aware() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True, f"{table.name}.{column.name} lacks timezone"


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
    assert isinstance(users.c.last_login_at.type, DateTime)
    assert users.c.last_login_at.type.timezone is True
