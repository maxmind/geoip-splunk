"""Shared utilities for the GeoIP app."""

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

# Whether the MaxMind databases ride the knowledge bundle to indexers is
# controlled through this [replicationAllowlist] key in distsearch.conf. The
# shipped default (default/distsearch.conf) is a pattern that matches
# nothing, keeping the databases out of the bundle; enabling "Run on
# indexers" overrides the key in local/distsearch.conf with the real
# pattern, since conf keys cannot be deleted through the REST API (see
# geoip_rh_settings.py).
MMDB_ALLOWLIST_KEY = "geoip_mmdb"

# Allow pattern: databases ride the bundle (indexer execution on).
MMDB_ALLOW_PATTERN = "apps/geoip/databases/*.mmdb"

# Allow-nothing pattern: matches no real file, so the databases stay out of
# the bundle (indexer execution off).
MMDB_ALLOW_NOTHING_PATTERN = "apps/geoip/databases/allow-nothing-placeholder"

# Conf coordinates of the "Run on indexers" toggle in geoip_settings.conf:
# the stanza (also the settings tab's REST id) and the field within it.
DISTRIBUTION_STANZA = "distribution"
RUN_ON_INDEXERS_FIELD = "run_on_indexers"

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
    DISTRIBUTION_STANZA: [
        {
            # Checkbox: stored as 1/0. UCC checkbox entities do not take
            # validators.
            "field": RUN_ON_INDEXERS_FIELD,
            "required": False,
            "encrypted": False,
            "default": 0,
            "validators": [],
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


def is_truthy(value: object) -> bool:
    """Whether a conf or REST value represents true.

    Splunk checkboxes and conf files store booleans as "1"/"0"; accept a
    few common spellings. Shared by the settings handler and the search
    command so both sides of the "Run on indexers" toggle agree.
    """
    return str(value).strip().lower() in ("1", "true", "yes")


def get_database_directory() -> Path:
    """Get the directory where MaxMind databases are stored.

    Database storage location: the app's databases/ directory, located
    relative to this file (<app root>/lib/geoip_utils.py -> <app
    root>/databases/).

    Why databases/ (a custom app-level directory):
    - It is outside search head cluster conf replication summaries, which
      capture only local/..., lookups/*, and metadata: members do not
      re-summarize hundreds of MB of binaries every minute, a destructive
      resync cannot rewrite a database in place mid-read, and no
      conf_replication_summary excludelist in server.conf (which
      AppInspect rejects) is needed to prevent any of that
    - It is outside Splunk's default knowledge bundle allowlist (app bin/
      and lookups/), so whether the databases replicate to indexers is
      controlled solely by the app's own distsearch.conf allowlist entry
    - Resolving the path relative to this file works both when the app is
      installed ($SPLUNK_HOME/etc/apps/geoip/) and when it runs from a
      knowledge bundle on an indexer
      ($SPLUNK_HOME/var/run/searchpeers/<bundle>/apps/geoip/)

    Why NOT other locations:
    - lookups/: rides the knowledge bundle for free via the default
      allowlist, but is swept into SHC replication summaries, and keeping
      the databases out of those requires the server.conf excludelist
      AppInspect rejects
    - local/data/ (the previous location): local/... is recursively
      included in SHC replication summaries too, and $SPLUNK_HOME-based
      resolution breaks on indexers where the app root is not under
      etc/apps
    - /default/ or package /data/: Overwritten on upgrades, read-only after
      install
    - $SPLUNK_HOME/var/lib/splunk/: Not a standard app data location
    - $SPLUNK_HOME/share/: System directory, not for app data
    - KV Store: Only for structured data, not binary files like .mmdb

    References:
    - https://docs.splunk.com/Documentation/Splunk/latest/Admin/Apparchitectureandobjectownership
    - https://docs.splunk.com/Documentation/Splunk/latest/Admin/Configurationfiledirectories
    - https://docs.splunk.com/Documentation/Splunk/latest/DistSearch/Whatsearchheadssend

    Returns:
        Path to the database directory.

    """
    # Allow override via environment variable (for testing)
    if env_dir := os.environ.get("MAXMIND_DB_DIR"):
        return Path(env_dir)

    return Path(__file__).resolve().parent.parent / "databases"


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
