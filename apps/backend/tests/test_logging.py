import logging

from app.core.logging import configure_logging
from app.db.session import engine


def test_http_client_logs_never_include_info_level_urls() -> None:
    configure_logging(debug=True)

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_database_engine_hides_bound_parameters() -> None:
    assert engine.sync_engine.hide_parameters is True
