import logging
from logging.config import dictConfig


def configure_logging(*, debug: bool = False) -> None:
    """Configure application logging in one place."""
    level = "DEBUG" if debug else "INFO"
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                }
            },
            "loggers": {
                # HTTPX logs complete URLs at INFO; WeChat credentials travel in query params.
                "httpcore": {"handlers": ["console"], "level": "WARNING", "propagate": False},
                "httpx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
            },
            "root": {"handlers": ["console"], "level": level},
        }
    )
    logging.getLogger(__name__).debug("Logging configured at %s level", level)
