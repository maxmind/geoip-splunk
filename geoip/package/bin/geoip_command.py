"""MaxMind database lookup streaming command for Splunk."""

import os
import re
import sys
from collections.abc import Iterator
from ipaddress import ip_network
from typing import Any, Protocol

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import maxminddb
from geoip_utils import (
    get_database_directory,
    get_fallback_logger,
    get_logger,
    get_run_on_indexers_setting,
    is_truthy,
)


class SearchInfo(Protocol):
    """Protocol for Splunk search info metadata."""

    app: str
    session_key: str
    sid: str


class Metadata(Protocol):
    """Protocol for Splunk command metadata."""

    searchinfo: SearchInfo


class Command(Protocol):
    """Protocol for Splunk streaming command objects."""

    databases: str
    field: str
    prefix: str
    metadata: Metadata


class Configuration(Protocol):
    """Protocol for the command's runtime configuration settings."""

    distributed: bool


class PreparableCommand(Protocol):
    """Protocol for the wrapper command object passed to prepare()."""

    configuration: Configuration
    metadata: Metadata


def prepare(command: PreparableCommand) -> None:
    """Decide whether this search distributes the command to the indexers.

    The generated wrapper (bin/geoip.py) calls this from its prepare()
    method, which the Splunk SDK runs before writing the getinfo reply -
    the reply that tells Splunk whether the command is distributable
    streaming (distributed=True) or search-head-only (distributed=False,
    reported as type=stateful).

    On the search head, the "Run on indexers" setting decides. On an
    indexer the search head has already made the decision, so report
    distributed streaming and never touch REST: the app's conf endpoints
    do not exist there. Indexer invocations are identified by the remote_
    prefix Splunk puts on their search id.
    """
    sid = str(getattr(command.metadata.searchinfo, "sid", "") or "")
    if sid.startswith("remote_"):
        command.configuration.distributed = True
        return
    command.configuration.distributed = _indexer_execution_enabled(command)


def _indexer_execution_enabled(command: PreparableCommand) -> bool:
    """Read the "Run on indexers" setting from geoip_settings.conf.

    The read goes through solnlib pinned to the geoip app's namespace
    (get_run_on_indexers_setting) rather than through command.service,
    which the SDK namespaces to the app the search was dispatched from -
    a read from there resolves the conf only via the app's
    export = system metadata.

    Any failure means search-head-only execution: a broken settings read
    must never take the search down, and running on the search head is
    always safe since the databases live there. Logging the failure must
    not take it down either: get_logger reads its log level from this
    same conf over REST, so whatever broke the settings read (splunkd
    unreachable, expired session key) may make it raise too.
    """
    session_key = command.metadata.searchinfo.session_key
    try:
        value = get_run_on_indexers_setting(session_key)
    except Exception:  # any failure means don't distribute
        try:
            logger = get_logger(session_key)
        except Exception:  # noqa: BLE001 - see the docstring
            logger = get_fallback_logger()
        logger.exception(
            "Failed to read the run_on_indexers setting; "
            "running on the search head only"
        )
        return False
    return is_truthy(value)


def stream(
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
        command: The Command instance with arguments:
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
    session_key = command.metadata.searchinfo.session_key

    for event in events:
        ip_address = event.get(field)

        if not ip_address:
            get_logger(session_key).debug("Event missing or empty field: %s", field)
            yield event
            continue

        found_any = False
        largest_prefix_len = 0

        for reader in readers:
            try:
                record, prefix_len = reader.get_with_prefix_len(ip_address)
            except ValueError:
                get_logger(session_key).debug("Invalid IP address: %s", ip_address)
                continue

            if not record:
                get_logger(session_key).debug(
                    "No record found for IP %s in database %s",
                    ip_address,
                    reader.metadata().database_type,
                )
                continue

            if not isinstance(record, dict):
                get_logger(session_key).debug(
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


# Cache of open database readers, keyed by database name.
#
# No mtime-based invalidation needed: Splunk spawns a fresh Python process
# for each search, so this cache starts empty and databases are always
# freshly opened. If the updater writes a new database file between
# searches, the next search automatically loads the updated version.
#
# The cache is still useful within a single search to avoid reopening
# the database for each batch of events (chunked streaming commands
# receive multiple batches in the same process).
_readers: dict[str, maxminddb.Reader] = {}

# Valid database name pattern (alphanumeric, underscores, and hyphens only)
_VALID_DB_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


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
        db_dir = get_database_directory()
        db_path = db_dir / f"{name}.mmdb"
        if not db_path.exists():
            msg = f"Database not found: {db_path}"
            raise FileNotFoundError(msg)
        _readers[name] = maxminddb.open_database(str(db_path))
    return _readers[name]


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
            # MaxMind orders subdivisions largest-to-smallest, so [-1]
            # is the most specific (e.g., city-level) subdivision.
            yield from _flatten_value(value[-1], f"{key}.-1")
    else:
        yield key, value
