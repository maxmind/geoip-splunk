"""Tests for geoipdebug_command.py.

Uses test data from the MaxMind-DB submodule.
"""

import platform
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import geoipdebug_command
import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch
    from geoipdebug_command import Configuration, Metadata, SearchInfo

_TEST_DATA_DIR = Path(__file__).parent / "data" / "test-data"


class MockSearchInfo:
    """Mock Splunk search info."""

    app: str = "geoip"
    session_key: str = "test_session_key"
    sid: str = "1234.56789"
    splunk_version: str = "10.2.0"


class MockMetadata:
    """Mock Splunk command metadata."""

    searchinfo: "SearchInfo"

    def __init__(self) -> None:
        self.searchinfo = MockSearchInfo()


class MockCommand:
    """Mock command object that provides the indexers argument."""

    metadata: "Metadata"

    def __init__(self, *, indexers: bool = False, sid: str = "1234.56789") -> None:
        self.indexers = indexers
        self.metadata = MockMetadata()
        self.metadata.searchinfo.sid = sid


class MockConfiguration:
    """Mock command configuration settings."""

    distributed: bool = True


class MockPreparableCommand:
    """Mock wrapper command object passed to prepare()."""

    configuration: "Configuration"
    metadata: "Metadata"

    def __init__(self, *, indexers: bool = False, sid: str = "1234.56789") -> None:
        self.indexers = indexers
        self.configuration = MockConfiguration()
        self.metadata = MockMetadata()
        self.metadata.searchinfo.sid = sid


def _by_component(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(event["component"], []).append(event)
    return grouped


def test_prepare_defaults_to_search_head_only() -> None:
    command = MockPreparableCommand(indexers=False)
    command.configuration.distributed = True

    geoipdebug_command.prepare(command)

    assert command.configuration.distributed is False


def test_prepare_distributes_when_indexers_argument_set() -> None:
    command = MockPreparableCommand(indexers=True)
    command.configuration.distributed = False

    geoipdebug_command.prepare(command)

    assert command.configuration.distributed is True


def test_prepare_reports_distributed_on_an_indexer() -> None:
    """On an indexer the search head has already made the decision; the
    indexers argument is not consulted again."""
    command = MockPreparableCommand(indexers=False, sid="remote_sh1_1234.56789")
    command.configuration.distributed = False

    geoipdebug_command.prepare(command)

    assert command.configuration.distributed is True


def test_generate_reports_a_configured_database() -> None:
    command = MockCommand()

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        return_value=["GeoIP2-Country-Test"],
    ):
        events = list(geoipdebug_command.generate(command))

    grouped = _by_component(events)
    assert sorted(grouped) == ["database", "settings", "system"]

    (event,) = grouped["database"]
    assert event["database"] == "GeoIP2-Country-Test"
    assert event["database_source"] == "configured"
    assert event["present"] == "true"
    assert event["file_path"].endswith("GeoIP2-Country-Test.mmdb")
    assert event["file_size_bytes"] > 0
    assert event["database_type"] == "GeoIP2-Country"
    assert event.get("error") is None
    # Both timestamps are RFC 3339 UTC.
    for field in ("file_mtime", "build_time"):
        parsed = datetime.fromisoformat(event[field])
        assert parsed.tzinfo == UTC

    hostname = socket.gethostname()
    for event in events:
        assert event["hostname"] == hostname
        assert event["_time"] > 0


def test_generate_reports_a_missing_configured_database() -> None:
    """A configured database the updater has not downloaded on this node
    is the failure mode the command exists to diagnose."""
    command = MockCommand()

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        return_value=["No-Such-DB"],
    ):
        events = list(geoipdebug_command.generate(command))

    (event,) = _by_component(events)["database"]
    assert event["database"] == "No-Such-DB"
    assert event["present"] == "false"
    assert event["error"] == "Database file not found on this node"
    assert event.get("build_time") is None


def test_generate_rejects_an_invalid_configured_database_name() -> None:
    """The same path-traversal guard as the geoip command: a configured
    name is joined onto the database directory, so it must not be able
    to point elsewhere."""
    command = MockCommand()

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        return_value=["../../etc/passwd"],
    ):
        events = list(geoipdebug_command.generate(command))

    (event,) = _by_component(events)["database"]
    assert event["database"] == "../../etc/passwd"
    assert event["present"] == "false"
    assert event["error"] == "Invalid database name"
    assert event.get("file_path") is None


def test_error_text_never_empty() -> None:
    """str() of a message-less exception is empty; the error field must
    still say something."""
    assert geoipdebug_command._error_text(ValueError("bad data")) == "bad data"
    assert geoipdebug_command._error_text(ValueError()) == "ValueError"


def test_generate_reports_a_corrupt_database_without_failing(
    tmp_path: Path,
    monkeypatch: "MonkeyPatch",
) -> None:
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))
    (tmp_path / "Corrupt.mmdb").write_bytes(b"not a maxmind database")
    command = MockCommand()

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        return_value=["Corrupt"],
    ):
        events = list(geoipdebug_command.generate(command))

    grouped = _by_component(events)
    (event,) = grouped["database"]
    assert event["present"] == "true"
    assert event["file_size_bytes"] > 0
    assert event["error"]
    assert event.get("build_time") is None
    # The broken file must not stop the other components.
    assert "system" in grouped
    assert "settings" in grouped


def test_generate_on_an_indexer_lists_bundle_files_and_skips_settings(
    tmp_path: Path,
    monkeypatch: "MonkeyPatch",
) -> None:
    """On an indexer the app's conf endpoints do not exist: the command
    must list the .mmdb files the knowledge bundle carries instead of
    reading the configured list, and must skip the settings event."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))
    shutil.copy(
        _TEST_DATA_DIR / "GeoIP2-Country-Test.mmdb",
        tmp_path / "GeoIP2-Country-Test.mmdb",
    )
    command = MockCommand(sid="remote_sh1_1234.56789")

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        new=MagicMock(),
    ) as read_mock:
        events = list(geoipdebug_command.generate(command))

    read_mock.assert_not_called()
    grouped = _by_component(events)
    assert sorted(grouped) == ["database", "system"]

    (event,) = grouped["database"]
    assert event["database"] == "GeoIP2-Country-Test"
    assert event["database_source"] == "directory"
    assert event["present"] == "true"

    (system,) = grouped["system"]
    assert system["on_indexer"] == "true"


def test_generate_lists_files_when_the_configured_list_read_fails(
    tmp_path: Path,
    monkeypatch: "MonkeyPatch",
) -> None:
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))
    shutil.copy(
        _TEST_DATA_DIR / "GeoIP2-Country-Test.mmdb",
        tmp_path / "GeoIP2-Country-Test.mmdb",
    )
    command = MockCommand()

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        side_effect=RuntimeError("splunkd unreachable"),
    ):
        events = list(geoipdebug_command.generate(command))

    grouped = _by_component(events)
    (event,) = grouped["database"]
    assert event["database"] == "GeoIP2-Country-Test"
    assert event["database_source"] == "directory"
    assert event["present"] == "true"

    (settings,) = grouped["settings"]
    assert settings["databases_configured"] == "unknown"


def test_system_event_reports_versions(
    tmp_path: Path,
    monkeypatch: "MonkeyPatch",
) -> None:
    app_conf = tmp_path / "app.conf"
    app_conf.write_text("[launcher]\nauthor = MaxMind\nversion = 9.9.9\n")
    monkeypatch.setattr(geoipdebug_command, "_APP_CONF_PATH", app_conf)
    command = MockCommand()

    with patch.object(
        geoipdebug_command, "get_configured_database_names", return_value=[]
    ):
        events = list(geoipdebug_command.generate(command))

    (event,) = _by_component(events)["system"]
    assert event["app_version"] == "9.9.9"
    assert event["splunk_version"] == "10.2.0"
    assert event["python_version"] == platform.python_version()
    assert event["database_directory"]
    assert event["on_indexer"] == "false"


@pytest.mark.parametrize(
    "content",
    [
        None,  # file does not exist
        "[launcher]\nauthor = MaxMind\n",  # no version key
    ],
)
def test_get_app_version_returns_unknown_when_unreadable(
    tmp_path: Path,
    monkeypatch: "MonkeyPatch",
    content: str | None,
) -> None:
    app_conf = tmp_path / "app.conf"
    if content is not None:
        app_conf.write_text(content)
    monkeypatch.setattr(geoipdebug_command, "_APP_CONF_PATH", app_conf)

    with patch.object(
        geoipdebug_command, "get_logger_or_fallback", return_value=MagicMock()
    ) as logger_mock:
        result = geoipdebug_command._get_app_version("test_session_key")

    assert result == "unknown"
    # Not a silent degrade: the failure is logged.
    logger_mock.return_value.exception.assert_called_once()


def test_app_conf_path_resolves_in_the_source_tree() -> None:
    """Guards the bin/../default/app.conf layout the version read relies
    on: the packaged layout mirrors the source tree, so if this moves,
    every install would report app_version=unknown. build.sh checks the
    built app.conf carries the version key UCC writes there."""
    assert geoipdebug_command._APP_CONF_PATH.is_file()


def test_settings_event_reports_settings() -> None:
    command = MockCommand()

    with (
        patch.object(
            geoipdebug_command,
            "get_configured_database_names",
            return_value=["GeoLite2-ASN", "GeoLite2-Country"],
        ),
        patch.object(
            geoipdebug_command, "get_setting", return_value="DEBUG"
        ) as loglevel_mock,
        patch.object(
            geoipdebug_command, "get_run_on_indexers_setting", return_value="1"
        ) as setting_mock,
        patch.object(
            geoipdebug_command, "has_account_credentials", return_value=True
        ) as credentials_mock,
    ):
        events = list(geoipdebug_command.generate(command))

    loglevel_mock.assert_called_once_with("test_session_key", "logging", "loglevel")
    setting_mock.assert_called_once_with("test_session_key")
    credentials_mock.assert_called_once_with("test_session_key")
    (event,) = _by_component(events)["settings"]
    assert event["loglevel"] == "DEBUG"
    assert event["run_on_indexers"] == "true"
    assert event["databases_configured"] == "GeoLite2-ASN,GeoLite2-Country"
    assert event["credentials_configured"] == "true"


def test_settings_event_reports_the_shipped_defaults() -> None:
    """A fresh install reads the values UCC ships in
    default/geoip_settings.conf: loglevel INFO, run_on_indexers 0, and
    an empty account stanza."""
    command = MockCommand()

    with (
        patch.object(
            geoipdebug_command, "get_configured_database_names", return_value=[]
        ),
        patch.object(geoipdebug_command, "get_setting", return_value="INFO"),
        patch.object(
            geoipdebug_command, "get_run_on_indexers_setting", return_value="0"
        ),
        patch.object(geoipdebug_command, "has_account_credentials", return_value=False),
    ):
        events = list(geoipdebug_command.generate(command))

    (event,) = _by_component(events)["settings"]
    assert event["loglevel"] == "INFO"
    assert event["run_on_indexers"] == "false"
    assert event["credentials_configured"] == "false"


def test_settings_event_loglevel_unknown_when_the_key_is_missing() -> None:
    """The shipped default conf always carries a loglevel value, so the
    key reading as None means something abnormal, not a default."""
    command = MockCommand()

    with (
        patch.object(
            geoipdebug_command, "get_configured_database_names", return_value=[]
        ),
        patch.object(geoipdebug_command, "get_setting", return_value=None),
        patch.object(
            geoipdebug_command, "get_run_on_indexers_setting", return_value="0"
        ),
        patch.object(geoipdebug_command, "has_account_credentials", return_value=False),
    ):
        events = list(geoipdebug_command.generate(command))

    (event,) = _by_component(events)["settings"]
    assert event["loglevel"] == "unknown"


def test_generate_migrates_legacy_databases_on_the_search_head() -> None:
    """After an upgrade the databases may still be in the pre-1.2.0
    location; without the migration the command would report every
    database as present=false while the geoip command (which also
    migrates) works."""
    command = MockCommand()

    with (
        patch.object(
            geoipdebug_command, "get_configured_database_names", return_value=[]
        ),
        patch.object(geoipdebug_command, "migrate_legacy_databases") as migrate_mock,
    ):
        list(geoipdebug_command.generate(command))

    migrate_mock.assert_called_once()


def test_generate_on_an_indexer_does_not_migrate() -> None:
    """On an indexer the app runs from the knowledge bundle and has no
    legacy directory; the command must not try to migrate there."""
    command = MockCommand(sid="remote_sh1_1234.56789")

    with patch.object(geoipdebug_command, "migrate_legacy_databases") as migrate_mock:
        list(geoipdebug_command.generate(command))

    migrate_mock.assert_not_called()


def test_generate_reports_no_databases_when_none_are_configured(
    tmp_path: Path,
    monkeypatch: "MonkeyPatch",
) -> None:
    """An empty configured list means no database events. It must not
    fall back to listing whatever files sit in the directory - that is
    only for nodes where the configured list is unreadable."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))
    (tmp_path / "Stray-File.mmdb").write_bytes(b"not a configured database")
    command = MockCommand()

    with patch.object(
        geoipdebug_command, "get_configured_database_names", return_value=[]
    ):
        events = list(geoipdebug_command.generate(command))

    assert "database" not in _by_component(events)


def test_settings_event_degrades_to_unknown_on_failures() -> None:
    """The logger lookup is broken too (at the geoip_utils level, so the
    real get_logger_or_fallback absorbs the raise): whatever broke the
    settings reads may break get_logger's conf read the same way, and the
    degradation to unknown must not depend on it."""
    import geoip_utils  # noqa: PLC0415

    command = MockCommand()

    with (
        patch.object(
            geoipdebug_command, "get_configured_database_names", return_value=[]
        ),
        patch.object(
            geoip_utils,
            "get_logger",
            side_effect=RuntimeError("no splunkd"),
        ),
        patch.object(
            geoipdebug_command,
            "get_setting",
            side_effect=RuntimeError("no splunkd"),
        ),
        patch.object(
            geoipdebug_command,
            "get_run_on_indexers_setting",
            side_effect=RuntimeError("no splunkd"),
        ),
        patch.object(
            geoipdebug_command,
            "has_account_credentials",
            side_effect=RuntimeError("no splunkd"),
        ),
    ):
        events = list(geoipdebug_command.generate(command))

    (event,) = _by_component(events)["settings"]
    assert event["loglevel"] == "unknown"
    assert event["run_on_indexers"] == "unknown"
    assert event["databases_configured"] == ""
    assert event["credentials_configured"] == "unknown"


def test_no_event_carries_credential_values() -> None:
    """Only whether credentials are configured is reported, never the
    account_id or license_key values themselves.

    Runs the real has_account_credentials over a conf read that returns
    distinctive decrypted values, then checks no event value contains
    them - the failure mode is a value leaking into some field, not a
    field literally named account_id."""
    import geoip_utils  # noqa: PLC0415

    account_id = "999888777"
    license_key = "wJalrXUtnFEMIexampleKEY"
    command = MockCommand()

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
        patch.object(
            geoipdebug_command, "get_configured_database_names", return_value=[]
        ),
        patch.object(geoipdebug_command, "get_setting", return_value=None),
        patch.object(
            geoipdebug_command, "get_run_on_indexers_setting", return_value=None
        ),
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get.return_value = {
            "account_id": account_id,
            "license_key": license_key,
        }
        events = list(geoipdebug_command.generate(command))

    (settings,) = _by_component(events)["settings"]
    assert settings["credentials_configured"] == "true"
    for event in events:
        for key, value in event.items():
            assert account_id not in str(value), key
            assert license_key not in str(value), key


def test_generate_gives_every_event_the_same_fields() -> None:
    """The SDK's record writer locks the output field set to the first
    record's keys, so an event missing a field another event has would
    silently lose it (verified on a live cluster)."""
    command = MockCommand()

    with patch.object(
        geoipdebug_command,
        "get_configured_database_names",
        return_value=["GeoIP2-Country-Test"],
    ):
        events = list(geoipdebug_command.generate(command))

    field_sets = {frozenset(event) for event in events}
    assert len(field_sets) == 1
