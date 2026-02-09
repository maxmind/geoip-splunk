"""Shared utilities for the GeoIP add-on."""

import logging
import os
from functools import lru_cache
from pathlib import Path

try:
    from solnlib import conf_manager
    from solnlib import log as solnlib_log

    _HAS_SOLNLIB = True
except ImportError:
    _HAS_SOLNLIB = False


APP_NAME = "geoip"
CONF_NAME = f"{APP_NAME}_settings"

# Field specifications for the settings REST handler (geoip_rh_settings.py).
# That file builds RestField objects from these specs. Tests compare these
# specs against globalConfig.json to catch drift between the two files.
SETTINGS_FIELD_SPECS = {
    "account": [
        {
            "field": "account_id",
            "required": True,
            "encrypted": True,
            "default": None,
            "validators": [
                {"type": "regex", "pattern": r"^[0-9]+$"},
                {"type": "string", "min_len": 1, "max_len": 20},
            ],
        },
        {
            "field": "license_key",
            "required": True,
            "encrypted": True,
            "default": None,
            "validators": [
                {"type": "regex", "pattern": r"^[A-Za-z0-9_]+$"},
                {"type": "string", "min_len": 8, "max_len": 100},
            ],
        },
    ],
    "logging": [
        {
            "field": "loglevel",
            "required": True,
            "encrypted": False,
            "default": "INFO",
            "validators": [
                {
                    "type": "regex",
                    "pattern": r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
                },
            ],
        },
    ],
}


def get_database_directory() -> Path:
    """Get the directory where MaxMind databases are stored.

    Database storage location: $SPLUNK_HOME/etc/apps/geoip/local/data/

    Why /local/data/:
    - The /local/ directory is preserved across add-on upgrades
    - Apps can write to their own /local/ directory in both Enterprise and Cloud
    - Using a /data/ subdirectory keeps databases separate from .conf files

    Why NOT other locations:
    - /default/ or package /data/: Overwritten on upgrades, read-only after install
    - $SPLUNK_HOME/var/lib/splunk/: Not a standard app data location
    - $SPLUNK_HOME/share/: System directory, not for app data
    - KV Store: Only for structured data, not binary files like .mmdb

    References:
    - https://docs.splunk.com/Documentation/Splunk/latest/Admin/Apparchitectureandobjectownership
    - https://docs.splunk.com/Documentation/Splunk/latest/Admin/Configurationfiledirectories

    Returns:
        Path to the database directory.

    """
    # Allow override via environment variable (for testing)
    if env_dir := os.environ.get("MAXMIND_DB_DIR"):
        return Path(env_dir)

    splunk_home = os.environ.get("SPLUNK_HOME", "/opt/splunk")
    return Path(splunk_home, "etc", "apps", APP_NAME, "local", "data")


def get_fallback_logger() -> logging.Logger:
    """Get a basic logger for use when no session key is available.

    The log level is hardcoded to INFO since without a session key we
    cannot read the user's configured level from Splunk's REST API.
    """
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    return logger


@lru_cache(maxsize=1)
def get_logger(session_key: str) -> logging.Logger:
    """Get a logger configured with the app's log level setting.

    The session key is required to read the user's configured log level
    from Splunk's REST API. Without it, the log level would be hardcoded
    and the Logging tab in the UI would have no effect.

    The result is cached to avoid repeated REST API calls. Only one logger
    is cached; concurrent searches with different session keys will evict
    each other's cached loggers, but this is acceptable since the log level
    setting is global anyway.
    """
    if not _HAS_SOLNLIB:
        return get_fallback_logger()

    logger: logging.Logger = solnlib_log.Logs().get_logger(APP_NAME)
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=APP_NAME,
        conf_name=CONF_NAME,
    )
    logger.setLevel(log_level)
    return logger
