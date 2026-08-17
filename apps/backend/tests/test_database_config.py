import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.db.session import _database_engine_options, _set_mysql_session_timezone, engine


def test_database_url_uses_asyncmy_and_encodes_credentials() -> None:
    settings = Settings(
        _env_file=None,
        db_host="mysql.internal",
        db_port=3307,
        db_user="app-user",
        db_password=SecretStr("p@ss/word"),
        db_name="meetup_vote",
    )

    assert settings.database_url.drivername == "mysql+asyncmy"
    assert settings.database_url.host == "mysql.internal"
    assert settings.database_url.port == 3307
    assert settings.database_url.username == "app-user"
    assert settings.database_url.password == "p@ss/word"
    assert settings.database_url.database == "meetup_vote"
    assert settings.database_url.query == {"charset": "utf8mb4"}
    assert "p%40ss%2Fword" in settings.database_url.render_as_string(hide_password=False)


@pytest.mark.parametrize("field_name", ["db_host", "db_user", "db_name"])
def test_database_connection_values_must_not_be_blank(field_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field_name: "   "})


def test_database_engine_options_are_bounded_for_cloud_hosting() -> None:
    settings = Settings(
        _env_file=None,
        db_pool_size=4,
        db_max_overflow=1,
        db_pool_timeout_seconds=20,
        db_pool_recycle_seconds=900,
        db_connect_timeout_seconds=8,
    )

    assert _database_engine_options(settings) == {
        "echo": False,
        "hide_parameters": True,
        "pool_pre_ping": True,
        "pool_size": 4,
        "max_overflow": 1,
        "pool_timeout": 20,
        "pool_recycle": 900,
        "isolation_level": "READ COMMITTED",
        "connect_args": {"connect_timeout": 8},
    }


def test_default_engine_is_mysql_and_hides_parameters() -> None:
    assert engine.url.drivername == "mysql+asyncmy"
    assert engine.sync_engine.hide_parameters is True


def test_mysql_connections_are_initialized_in_utc() -> None:
    executed: list[str] = []

    class FakeCursor:
        def execute(self, statement: str) -> None:
            executed.append(statement)

        def close(self) -> None:
            executed.append("closed")

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    _set_mysql_session_timezone(FakeConnection(), None)

    assert executed == ["SET SESSION time_zone = '+00:00'", "closed"]
