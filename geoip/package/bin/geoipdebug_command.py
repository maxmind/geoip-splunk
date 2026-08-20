"""MaxMind GeoIP app diagnostics generating command for Splunk."""

import configparser
import os
import platform
import socket
import sys
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import maxminddb
from geoip_utils import (
    fill_missing_event_fields,
    get_configured_database_names,
    get_database_directory,
    get_logger_or_fallback,
    get_run_on_indexers_setting,
    get_setting,
    has_account_credentials,
    is_truthy,
    is_valid_database_name,
    migrate_legacy_databases,
)


class SearchInfo(Protocol):
    """Protocol for Splunk search info metadata."""

    app: str
    session_key: str
    sid: str
    splunk_version: str


class Metadata(Protocol):
    """Protocol for Splunk command metadata."""

    searchinfo: SearchInfo


class Command(Protocol):
    """Protocol for Splunk generating command objects."""

    indexers: bool
    metadata: Metadata


class Configuration(Protocol):
    """Protocol for the command's runtime configuration settings."""

    distributed: bool


class PreparableCommand(Protocol):
    """Protocol for the wrapper command object passed to prepare()."""

    indexers: bool
    configuration: Configuration
    metadata: Metadata


def prepare(command: PreparableCommand) -> None:
    """Decide whether this search distributes the command to the indexers.

    The generated wrapper (bin/geoipdebug.py) calls this from its
    prepare() method, which the Splunk SDK runs before writing the getinfo
    reply - the reply that tells Splunk whether the command is
    distributable streaming (distributed=True) or search-head-only
    (distributed=False, reported as type=stateful).

    Unlike the geoip command, distribution is decided by the command's own
    indexers argument, not the "Run on indexers" setting: inspecting what
    the knowledge bundle carries is useful precisely when that setting and
    the bundle disagree. The SDK parses the arguments before calling
    prepare(), so the option is available here, and no REST read is
    needed.

    On an indexer the search head has already made the decision, so report
    distributed streaming. Indexer invocations are identified by the
    remote_ prefix Splunk puts on their search id.
    """
    sid = str(getattr(command.metadata.searchinfo, "sid", "") or "")
    if sid.startswith("remote_"):
        command.configuration.distributed = True
        return
    command.configuration.distributed = bool(command.indexers)


def generate(command: Command) -> Iterator[dict[str, Any]]:
    """Generate diagnostic events about the GeoIP app on this node.

    Yields one event per item, distinguished by the component field:

    - database: one event per configured database (build time, type, and
      file details). On an indexer, where the configured list is
      unreadable, one event per .mmdb file the knowledge bundle carries
      instead.
    - system: app, Splunk, and Python versions plus the database
      directory.
    - settings: non-secret app settings (search head only; the app's conf
      endpoints do not exist on an indexer). Credential values are never
      output.

    Every event carries the hostname, so distributed runs show which node
    reported what. Failures never take the search down: a broken database
    yields an error field on its event, and a failed settings read yields
    "unknown".
    """
    sid = str(getattr(command.metadata.searchinfo, "sid", "") or "")
    on_indexer = sid.startswith("remote_")
    # Defensively, like sid above: the session key is only used for conf
    # reads and logging, both of which have fallbacks.
    session_key = str(getattr(command.metadata.searchinfo, "session_key", "") or "")

    configured = None
    if not on_indexer:
        # After an upgrade the databases may still be in the pre-1.2.0
        # location; without this, every database would report
        # present=false while the geoip command (which also migrates)
        # works. Never on an indexer: the app runs from the knowledge
        # bundle there and has no legacy directory.
        migrate_legacy_databases(get_logger_or_fallback(session_key))
        configured = _get_configured_databases(session_key)

    events = list(_database_events(configured))
    events.append(
        _system_event(command, session_key=session_key, on_indexer=on_indexer)
    )
    if not on_indexer:
        events.append(_settings_event(session_key, configured))

    hostname = socket.gethostname()
    now = time.time()
    for event in events:
        event["hostname"] = hostname
        event["_time"] = now

    # The SDK's record writer locks the output field set to the first
    # record's keys, so every event must carry every field or the
    # components emitted after the first silently lose the fields the
    # first does not have.
    fill_missing_event_fields(events)

    yield from events


def _get_configured_databases(session_key: str) -> list[str] | None:
    """Read the configured database list, or None if the read fails."""
    try:
        return get_configured_database_names(session_key)
    except Exception:  # noqa: BLE001 - a broken conf read must not fail the search
        _log_exception(session_key, "Failed to read the configured database list")
        return None


def _database_events(configured: list[str] | None) -> Iterator[dict[str, Any]]:
    """Yield one database event per database.

    With a configured list, every configured database gets an event, so a
    database the updater has not downloaded on this node shows up as
    present=false. Without one (on an indexer, or after a failed conf
    read), the .mmdb files in the database directory are listed instead -
    on an indexer that is exactly what the knowledge bundle carries.

    Each event says which of the two it was in database_source
    ("configured" or "directory"), so a reader can tell "every configured
    database, downloaded or not" apart from "whatever files are here".
    """
    db_dir = get_database_directory()
    if configured is None:
        for path in sorted(db_dir.glob("*.mmdb")):
            yield _database_event(path.stem, path, source="directory")
        return
    for name in sorted(configured):
        if not is_valid_database_name(name):
            # The same guard as the geoip command: the name is about to
            # be joined onto the database directory.
            yield {
                "component": "database",
                "database": name,
                "database_source": "configured",
                "present": _bool_text(value=False),
                "error": "Invalid database name",
            }
            continue
        yield _database_event(name, db_dir / f"{name}.mmdb", source="configured")


def _database_event(name: str, path: Path, *, source: str) -> dict[str, Any]:
    """Build the event for one database, resilient to a broken file."""
    event: dict[str, Any] = {
        "component": "database",
        "database": name,
        "database_source": source,
        "file_path": str(path),
    }

    try:
        stat_result = path.stat()
    except FileNotFoundError:
        event["present"] = _bool_text(value=False)
        event["error"] = "Database file not found on this node"
        return event
    except OSError as exc:
        event["present"] = _bool_text(value=False)
        event["error"] = _error_text(exc)
        return event

    event["present"] = _bool_text(value=True)
    event["file_size_bytes"] = stat_result.st_size
    event["file_mtime"] = _rfc3339_utc(stat_result.st_mtime)

    try:
        with maxminddb.open_database(str(path)) as reader:
            metadata = reader.metadata()
        event["database_type"] = metadata.database_type
        event["build_time"] = _rfc3339_utc(metadata.build_epoch)
    except Exception as exc:  # noqa: BLE001 - a corrupt file must not fail the search
        event["error"] = _error_text(exc)

    return event


def _error_text(exc: BaseException) -> str:
    """Format an exception for an error field.

    str() of a message-less exception is empty, which would leave an
    error field that says nothing; fall back to the exception type.
    """
    return str(exc) or type(exc).__name__


def _rfc3339_utc(epoch: float) -> str:
    """Format a Unix epoch as an RFC 3339 UTC timestamp."""
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def _system_event(
    command: Command, *, session_key: str, on_indexer: bool
) -> dict[str, Any]:
    """Build the event describing this node's software versions."""
    splunk_version = str(
        getattr(command.metadata.searchinfo, "splunk_version", "") or ""
    )
    return {
        "component": "system",
        "app_version": _get_app_version(session_key),
        "splunk_version": splunk_version or "unknown",
        "python_version": platform.python_version(),
        "database_directory": str(get_database_directory()),
        "on_indexer": _bool_text(value=on_indexer),
    }


# The app version lands in default/app.conf at build time (UCC writes it
# from globalConfig.json; build.sh verifies it did). Resolved relative to
# this file so it works both installed (etc/apps/geoip/) and in a knowledge
# bundle on an indexer (.conf files ride the bundle by default).
# Module-level so tests can point it elsewhere.
_APP_CONF_PATH = Path(__file__).resolve().parent.parent / "default" / "app.conf"


def _get_app_version(session_key: str) -> str:
    """Read the app version from default/app.conf, or "unknown".

    Reads the file explicitly rather than through configparser.read(),
    which silently ignores files it cannot open - a missing app.conf
    would degrade to "unknown" with no trace. Here every failure (file
    unreadable, no [launcher] section, no version key) is logged.
    """
    try:
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        parser.read_string(_APP_CONF_PATH.read_text(encoding="utf-8"))
        return parser["launcher"]["version"]
    except Exception:  # noqa: BLE001 - diagnostics must not fail the search
        _log_exception(session_key, "Failed to read the app version from app.conf")
        return "unknown"


def _settings_event(session_key: str, configured: list[str] | None) -> dict[str, Any]:
    """Build the event with the app's non-secret settings.

    The credential values (account_id, license_key) are never output:
    has_account_credentials reads them decrypted only to compute the
    boolean, and they never leave that function.
    """
    return {
        "component": "settings",
        # The raw configured value (default/ and local/ merged), read
        # directly: the logger's own read (solnlib's get_log_level)
        # swallows failures into the INFO default, which would hide
        # exactly what this event is for. The shipped default conf
        # always carries a value, so None means the key vanished.
        "loglevel": _read_setting(
            session_key,
            "the log level",
            lambda: get_setting(session_key, "logging", "loglevel") or "unknown",
        ),
        "run_on_indexers": _read_setting(
            session_key,
            "the run_on_indexers setting",
            lambda: _bool_text(
                value=is_truthy(get_run_on_indexers_setting(session_key))
            ),
        ),
        "databases_configured": (
            ",".join(configured) if configured is not None else "unknown"
        ),
        "credentials_configured": _read_setting(
            session_key,
            "the account configuration",
            lambda: _bool_text(value=has_account_credentials(session_key)),
        ),
    }


def _read_setting(
    session_key: str,
    description: str,
    read: Callable[[], object],
) -> object:
    """Run one settings read, degrading to "unknown" on any failure."""
    try:
        return read()
    except Exception:  # noqa: BLE001 - a broken read must not fail the search
        _log_exception(session_key, f"Failed to read {description}")
        return "unknown"


def _bool_text(*, value: bool) -> str:
    """Format a boolean event value as the string "true" or "false".

    The SDK's record writer serializes a Python bool as 1/0. Mixed with
    the "unknown" some fields degrade to, the field would have no stable
    type, and the documented true/false would match nothing.
    """
    return "true" if value else "false"


def _log_exception(session_key: str, message: str) -> None:
    """Log the current exception without letting logging itself raise."""
    get_logger_or_fallback(session_key).exception(message)
