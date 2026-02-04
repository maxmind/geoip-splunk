"""Shared utilities for the GeoIP add-on."""

import logging
from functools import lru_cache

try:
    from solnlib import conf_manager
    from solnlib import log as solnlib_log

    _HAS_SOLNLIB = True
except ImportError:
    _HAS_SOLNLIB = False


APP_NAME = "geoip"
CONF_NAME = f"{APP_NAME}_settings"


@lru_cache(maxsize=1)
def get_logger(session_key: str) -> logging.Logger:
    """Get a logger configured with the app's log level setting.

    The result is cached to avoid repeated REST API calls. Only one logger
    is cached; concurrent searches with different session keys will evict
    each other's cached loggers, but this is acceptable since the log level
    setting is global anyway.
    """
    if not _HAS_SOLNLIB:
        fallback = logging.getLogger(APP_NAME)
        fallback.setLevel(logging.INFO)
        return fallback

    logger: logging.Logger = solnlib_log.Logs().get_logger(APP_NAME)
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=APP_NAME,
        conf_name=CONF_NAME,
    )
    logger.setLevel(log_level)
    return logger
