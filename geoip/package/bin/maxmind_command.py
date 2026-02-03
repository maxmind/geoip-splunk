"""MaxMind database lookup streaming command for Splunk."""

import logging
import os
import re
import sys
from collections.abc import Iterator
from ipaddress import ip_network
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import maxminddb

try:
    from solnlib import conf_manager
    from solnlib import log as solnlib_log

    _HAS_SOLNLIB = True
except ImportError:
    _HAS_SOLNLIB = False


class SearchInfo(Protocol):
    """Protocol for Splunk search info metadata."""

    app: str
    session_key: str


class Metadata(Protocol):
    """Protocol for Splunk command metadata."""

    searchinfo: SearchInfo


class Command(Protocol):
    """Protocol for Splunk streaming command objects."""

    databases: str
    field: str
    prefix: str
    metadata: Metadata


# Cache of open database readers, keyed by database name
_readers: dict[str, maxminddb.Reader] = {}

# Valid database name pattern (alphanumeric and hyphens only)
_VALID_DB_NAME = re.compile(r"^[A-Za-z0-9-]+$")

# Directory containing MaxMind databases
# TODO: We need to be able to re-open databases when there are updates.
# TODO: We need to be able to download databases rather than assume they are
# available in the add-on directly.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_db_dir = os.environ.get(
    "MAXMIND_DB_DIR",
    os.path.join(_script_dir, "..", "data"),
)


def _get_reader(name: str) -> maxminddb.Reader:
    """Get a database reader, opening it if not already cached.

    Args:
        name: The database name (e.g., 'GeoIP2-Country')

    Returns:
        The maxminddb.Reader for the database

    Raises:
        ValueError: If the database name contains invalid characters
        FileNotFoundError: If the database file doesn't exist

    """
    if not _VALID_DB_NAME.match(name):
        msg = f"Invalid database name: {name}"
        raise ValueError(msg)
    if name not in _readers:
        db_path = Path(_db_dir, f"{name}.mmdb")
        if not db_path.exists():
            msg = f"Database not found: {db_path}"
            raise FileNotFoundError(msg)
        _readers[name] = maxminddb.open_database(str(db_path))
    return _readers[name]


def stream(  # noqa: C901
    command: Command,
    events: Iterator[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Enrich events with data from MaxMind databases.

    Looks up the IP address in each specified database and adds all fields
    found to the event using dot-notation (e.g., country.iso_code,
    country.names.en, continent.code). Also adds a 'network' field with the
    most specific matched CIDR block across all databases.

    When multiple databases contain the same field, the last database in the
    list wins.

    If no result is found in any database (invalid IP, IP not in database, or
    missing IP field), the event is yielded unchanged.

    Args:
        command: The MaxmindCommand instance with arguments:
            databases: Comma-separated list of database names to query
                (e.g., 'GeoIP2-Country,GeoIP2-Anonymous-IP').
            field: The event field containing the IP address to look up
                (default: 'ip').
            prefix: A prefix to prepend to all output field names
                (default: '').
        events: Generator of event dictionaries

    Yields:
        Event dictionaries, enriched with database fields when a match is found

    """
    database_names = [name.strip() for name in command.databases.split(",")]
    readers = [_get_reader(name) for name in database_names]
    field = command.field
    prefix = command.prefix
    logger: logging.Logger | None = None

    for event in events:
        ip_address = event.get(field)

        if not ip_address:
            if logger is None:
                logger = _get_logger(command.metadata.searchinfo.session_key)
            logger.debug("Event missing or empty field: %s", field)
            yield event
            continue

        found_any = False
        largest_prefix_len = 0

        for reader in readers:
            try:
                record, prefix_len = reader.get_with_prefix_len(ip_address)
            except ValueError:
                if logger is None:
                    logger = _get_logger(command.metadata.searchinfo.session_key)
                logger.debug("Invalid IP address: %s", ip_address)
                continue

            if not record:
                if logger is None:
                    logger = _get_logger(command.metadata.searchinfo.session_key)
                logger.debug(
                    "No record found for IP %s in database %s",
                    ip_address,
                    reader.metadata().database_type,
                )
                continue

            if not isinstance(record, dict):
                if logger is None:
                    logger = _get_logger(command.metadata.searchinfo.session_key)
                logger.debug(
                    "Record for IP %s is not a dict: %s",
                    ip_address,
                    type(record).__name__,
                )
                continue

            found_any = True

            for key, value in _flatten_record(record):
                event[f"{prefix}{key}"] = value

            largest_prefix_len = max(largest_prefix_len, prefix_len)

        if not found_any:
            yield event
            continue

        network = ip_network(f"{ip_address}/{largest_prefix_len}", strict=False)
        event[f"{prefix}network"] = str(network)

        yield event


_APP_NAME = "geoip"
_CONF_NAME = f"{_APP_NAME}_settings"


def _get_logger(session_key: str) -> logging.Logger:
    """Get a logger configured with the app's log level setting."""
    if not _HAS_SOLNLIB:
        fallback = logging.getLogger(_APP_NAME)
        fallback.setLevel(logging.INFO)
        return fallback

    logger: logging.Logger = solnlib_log.Logs().get_logger(_APP_NAME)
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=_APP_NAME,
        conf_name=_CONF_NAME,
    )
    logger.setLevel(log_level)
    return logger


def _flatten_record(record: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Flatten a nested record dict into dot-notation keys.

    Args:
        record: A dictionary that may contain nested dictionaries or lists

    Yields:
        Tuples of (flattened_key, value) for all leaf values

    Examples:
        {"country": {"iso_code": "US"}} -> [("country.iso_code", "US")]
        {"subdivisions": [{"iso_code": "CA"}]} -> [("subdivisions.0.iso_code", "CA")]

    """
    for key, value in record.items():
        yield from _flatten_value(value, key)


def _flatten_value(
    value: Any,  # noqa: ANN401
    key: str,
) -> Iterator[tuple[str, Any]]:
    """Flatten a value, recursing into dicts and lists.

    Args:
        value: The value to flatten (may be dict, list, or scalar)
        key: The key for this value

    Yields:
        Tuples of (flattened_key, value) for all leaf values

    """
    if isinstance(value, dict):
        for sub_key, sub_value in value.items():
            yield from _flatten_value(sub_value, f"{key}.{sub_key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _flatten_value(item, f"{key}.{i}")
        if value and key == "subdivisions":
            yield from _flatten_value(value[-1], f"{key}.-1")
    else:
        yield key, value
