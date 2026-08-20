"""Tests for the geoipupdate_input module."""

from __future__ import annotations

import gzip
import hashlib
import io
import logging
import sys
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import geoip_utils
import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_httpserver import HTTPServer

# Add the lib and bin directories to the path for testing
repo_root = Path(__file__).parent.parent
lib_dir = repo_root / "geoip" / "package" / "lib"
bin_dir = repo_root / "geoip" / "package" / "bin"
sys.path.insert(0, str(lib_dir))
sys.path.insert(0, str(bin_dir))

# Mock solnlib before importing geoipupdate_input since solnlib is not
# installed in the dev environment (it's only in the app's runtime deps)
mock_conf_manager = MagicMock()
mock_soln_exceptions = MagicMock()


class ConfManagerException(Exception):  # noqa: N818
    """Stand-in for solnlib.soln_exceptions.ConfManagerException."""


class ConfStanzaNotExistException(Exception):  # noqa: N818
    """Stand-in for solnlib.soln_exceptions.ConfStanzaNotExistException."""


mock_soln_exceptions.ConfManagerException = ConfManagerException
mock_soln_exceptions.ConfStanzaNotExistException = ConfStanzaNotExistException


mock_solnlib = MagicMock()
mock_solnlib.conf_manager = mock_conf_manager
mock_solnlib.soln_exceptions = mock_soln_exceptions
sys.modules["solnlib"] = mock_solnlib
sys.modules["solnlib.conf_manager"] = mock_conf_manager
sys.modules["solnlib.soln_exceptions"] = mock_soln_exceptions

# Now we can import geoipupdate_input since solnlib is mocked
from geoipupdate_input import (  # noqa: E402  # type: ignore[import-not-found]
    GeoIPUpdateInput,
    _get_account_credentials,
    _get_database_names,
    _run_update,
    _sync_replication_marker_from_settings,
)
from pygeoipupdate import Config as PyGeoIPUpdateConfig  # noqa: E402
from pygeoipupdate.errors import (  # noqa: E402  # type: ignore[import-not-found]
    GeoIPUpdateError,
)

# Test account ID used across tests
TEST_ACCOUNT_ID = 12345


def test_get_scheme() -> None:
    """Test that get_scheme returns the expected structure."""
    input_obj = GeoIPUpdateInput()
    scheme = input_obj.get_scheme()

    assert scheme["title"] == "GeoIP Database Update"
    assert scheme["description"] == "Downloads and updates MaxMind GeoIP databases"
    assert scheme["use_external_validation"] is False
    assert scheme["streaming_mode_xml"] is True
    assert scheme["use_single_instance"] is False
    assert scheme["args"] == ["run_only_one"]


def test_validate_input_does_nothing() -> None:
    """Test that validate_input accepts any input without raising."""
    input_obj = GeoIPUpdateInput()
    # Should not raise
    input_obj.validate_input(None)
    input_obj.validate_input({"anything": "here"})


def test_stream_events_returns_without_session_key() -> None:
    """Test that stream_events returns when no session key."""
    input_obj = GeoIPUpdateInput()

    # Mock inputs with empty session key
    inputs = MagicMock()
    inputs.metadata = {"session_key": ""}

    input_obj.stream_events(inputs, None)


def test_stream_events_returns_with_missing_session_key() -> None:
    """Test that stream_events returns when session key missing."""
    input_obj = GeoIPUpdateInput()

    # Mock inputs with no session key in metadata
    inputs = MagicMock()
    inputs.metadata = {}

    input_obj.stream_events(inputs, None)


def test_stream_events_handles_missing_credentials(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that stream_events logs warning when credentials not configured."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            side_effect=ValueError("Credentials not configured"),
        ),
    ):
        input_obj.stream_events(inputs, None)

    # Verify warning was logged
    mock_logger.warning.assert_called_once()
    assert "Skipping database update" in mock_logger.warning.call_args[0][0]


def test_stream_events_migrates_even_when_unconfigured(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Databases left in the pre-1.2.0 location must move on the next
    update run even before credentials are configured."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch("geoipupdate_input.migrate_legacy_databases") as migrate_mock,
        patch(
            "geoipupdate_input._get_account_credentials",
            side_effect=ValueError("Credentials not configured"),
        ),
    ):
        input_obj.stream_events(inputs, None)

    migrate_mock.assert_called_once_with(mock_logger)


def test_stream_events_survives_a_broken_logger(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """get_logger reads the log level over REST, so it can raise - and
    the migration, which needs no REST, must still run on a member where
    conf reads are broken. Broken at the geoip_utils level so the real
    get_logger_or_fallback absorbs the raise."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    with (
        patch.object(
            geoip_utils,
            "get_logger",
            side_effect=RuntimeError("splunkd unreachable"),
        ),
        patch("geoipupdate_input.migrate_legacy_databases") as migrate_mock,
        patch("geoipupdate_input._sync_replication_marker_from_settings") as sync_mock,
        patch(
            "geoipupdate_input._get_account_credentials",
            side_effect=ValueError("Credentials not configured"),
        ),
    ):
        input_obj.stream_events(inputs, None)

    fallback = geoip_utils.get_fallback_logger()
    migrate_mock.assert_called_once_with(fallback)
    sync_mock.assert_called_once_with("test_session_key", fallback)


def test_stream_events_syncs_the_marker_even_when_unconfigured(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """The bundle state marker must track the "Run on indexers" setting
    even before credentials are configured: the run right after a restart
    may be what makes the toggle's bundle change reach the indexers."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input.get_run_on_indexers_setting",
            return_value="1",
        ) as setting_mock,
        patch("geoipupdate_input.sync_replication_marker") as sync_mock,
        patch(
            "geoipupdate_input._get_account_credentials",
            side_effect=ValueError("Credentials not configured"),
        ),
    ):
        input_obj.stream_events(inputs, None)

    setting_mock.assert_called_once_with("test_session_key")
    sync_mock.assert_called_once()
    assert sync_mock.call_args.args[0]() is mock_logger
    assert sync_mock.call_args.kwargs == {"run_on_indexers": True}


def test_sync_from_settings_skips_when_the_setting_read_fails() -> None:
    """A failed settings read must not rewrite the marker (the current
    state is unknown, and a wrong write could rebuild the bundle) and
    must not take down the update run."""
    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch(
            "geoipupdate_input.get_run_on_indexers_setting",
            side_effect=RuntimeError("splunkd unreachable"),
        ),
        patch("geoipupdate_input.sync_replication_marker") as sync_mock,
    ):
        _sync_replication_marker_from_settings("test_session_key", mock_logger)

    sync_mock.assert_not_called()
    mock_logger.exception.assert_called_once()


def test_stream_events_handles_missing_databases(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that stream_events logs warning when no databases configured."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            return_value=(TEST_ACCOUNT_ID, "key"),
        ),
        patch(
            "geoipupdate_input._get_database_names",
            side_effect=ValueError("No databases configured"),
        ),
    ):
        input_obj.stream_events(inputs, None)

    mock_logger.warning.assert_called_once()
    assert "Skipping database update" in mock_logger.warning.call_args[0][0]


def test_stream_events_handles_geoipupdate_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that stream_events logs exception on GeoIPUpdateError."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            return_value=(TEST_ACCOUNT_ID, "key"),
        ),
        patch(
            "geoipupdate_input._get_database_names",
            return_value=["GeoLite2-Country"],
        ),
        patch(
            "geoipupdate_input._run_update",
            side_effect=GeoIPUpdateError("Download failed"),
        ),
        # Patched so its settings read (which fails without solnlib) does
        # not add a logger.exception call of its own.
        patch("geoipupdate_input._sync_replication_marker_from_settings"),
    ):
        input_obj.stream_events(inputs, None)

    mock_logger.exception.assert_called_once_with("Database update failed")


def test_stream_events_handles_unexpected_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that stream_events logs exception on unexpected errors."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            return_value=(TEST_ACCOUNT_ID, "key"),
        ),
        patch(
            "geoipupdate_input._get_database_names",
            return_value=["GeoLite2-Country"],
        ),
        patch(
            "geoipupdate_input._run_update",
            side_effect=RuntimeError("Something unexpected"),
        ),
        # Patched so its settings read (which fails without solnlib) does
        # not add a logger.exception call of its own.
        patch("geoipupdate_input._sync_replication_marker_from_settings"),
    ):
        input_obj.stream_events(inputs, None)

    mock_logger.exception.assert_called_once_with(
        "Unexpected error during database update"
    )


def test_stream_events_creates_database_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that stream_events creates the database directory if it doesn't exist."""
    db_dir = tmp_path / "subdir" / "data"
    monkeypatch.setenv("MAXMIND_DB_DIR", str(db_dir))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            return_value=(TEST_ACCOUNT_ID, "key"),
        ),
        patch(
            "geoipupdate_input._get_database_names",
            return_value=["GeoLite2-Country"],
        ),
        patch(
            "geoipupdate_input._run_update",
        ),
    ):
        input_obj.stream_events(inputs, None)

    assert db_dir.exists()
    assert db_dir.is_dir()


def test_stream_events_logs_success(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that stream_events logs success message after update completes."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            return_value=(TEST_ACCOUNT_ID, "key"),
        ),
        patch(
            "geoipupdate_input._get_database_names",
            return_value=["GeoLite2-Country"],
        ),
        patch(
            "geoipupdate_input._run_update",
        ),
    ):
        input_obj.stream_events(inputs, None)

    mock_logger.info.assert_called_with("Database update completed successfully")


def test_get_account_credentials_returns_credentials() -> None:
    """Test _get_account_credentials returns credentials from config."""
    mock_stanza = {"account_id": "12345", "license_key": "secret_key"}

    mock_conf = MagicMock()
    mock_conf.get.return_value = mock_stanza

    mock_cfm = MagicMock()
    mock_cfm.get_conf.return_value = mock_conf

    mock_conf_manager.ConfManager.return_value = mock_cfm

    account_id, license_key = _get_account_credentials("session_key")

    assert account_id == TEST_ACCOUNT_ID
    assert license_key == "secret_key"


def test_get_account_credentials_raises_when_missing_account_id() -> None:
    """Test _get_account_credentials raises ValueError when account_id missing."""
    mock_stanza = {"account_id": "", "license_key": "secret_key"}

    mock_conf = MagicMock()
    mock_conf.get.return_value = mock_stanza

    mock_cfm = MagicMock()
    mock_cfm.get_conf.return_value = mock_conf

    mock_conf_manager.ConfManager.return_value = mock_cfm

    with pytest.raises(ValueError, match="credentials not configured"):
        _get_account_credentials("session_key")


def test_get_account_credentials_raises_when_missing_license_key() -> None:
    """Test _get_account_credentials raises ValueError when license_key missing."""
    mock_stanza = {"account_id": "12345", "license_key": ""}

    mock_conf = MagicMock()
    mock_conf.get.return_value = mock_stanza

    mock_cfm = MagicMock()
    mock_cfm.get_conf.return_value = mock_conf

    mock_conf_manager.ConfManager.return_value = mock_cfm

    with pytest.raises(ValueError, match="credentials not configured"):
        _get_account_credentials("session_key")


def test_get_account_credentials_raises_when_account_id_not_numeric() -> None:
    """Test _get_account_credentials raises ValueError for non-numeric account ID."""
    mock_stanza = {"account_id": "abc", "license_key": "secret_key"}

    mock_conf = MagicMock()
    mock_conf.get.return_value = mock_stanza

    mock_cfm = MagicMock()
    mock_cfm.get_conf.return_value = mock_conf

    mock_conf_manager.ConfManager.return_value = mock_cfm

    with pytest.raises(ValueError, match="account ID must be a number"):
        _get_account_credentials("session_key")


def test_get_account_credentials_raises_when_conf_missing() -> None:
    """Test _get_account_credentials raises ValueError on fresh install."""
    mock_conf = MagicMock()
    mock_conf.get.side_effect = ConfStanzaNotExistException("account")

    mock_cfm = MagicMock()
    mock_cfm.get_conf.return_value = mock_conf

    mock_conf_manager.ConfManager.return_value = mock_cfm

    with pytest.raises(ValueError, match="credentials not configured"):
        _get_account_credentials("session_key")


def test_get_database_names_returns_database_list() -> None:
    """Test _get_database_names returns list of database names."""
    with patch(
        "geoipupdate_input.get_configured_database_names",
        return_value=["GeoLite2-Country", "GeoLite2-City"],
    ):
        databases = _get_database_names("session_key")

    assert databases == ["GeoLite2-Country", "GeoLite2-City"]


def test_get_database_names_raises_when_empty() -> None:
    """Test _get_database_names raises ValueError when no databases configured."""
    with (
        patch("geoipupdate_input.get_configured_database_names", return_value=[]),
        pytest.raises(ValueError, match="No databases configured"),
    ):
        _get_database_names("session_key")


def test_run_update_logs_updated_databases(tmp_path: Path) -> None:
    """Test _run_update logs info for updated databases."""
    mock_logger = MagicMock(spec=logging.Logger)

    mock_result = MagicMock()
    mock_result.edition_id = "GeoLite2-Country"
    mock_result.was_updated = True
    mock_result.old_hash = "abc123"
    mock_result.new_hash = "def456"

    mock_updater = MagicMock()
    mock_updater.run = AsyncMock(return_value=[mock_result])
    mock_updater.__aenter__ = AsyncMock(return_value=mock_updater)
    mock_updater.__aexit__ = AsyncMock(return_value=None)

    with patch("geoipupdate_input.Updater", return_value=mock_updater):
        _run_update(
            account_id=TEST_ACCOUNT_ID,
            license_key="key",
            edition_ids=["GeoLite2-Country"],
            database_directory=tmp_path,
            logger=mock_logger,
        )

    # Check starting message
    mock_logger.info.assert_any_call(
        "Starting database update for editions: %s",
        "GeoLite2-Country",
    )

    # Check updated message
    mock_logger.info.assert_any_call(
        "Updated %s: %s -> %s",
        "GeoLite2-Country",
        "abc123",
        "def456",
    )


def test_run_update_logs_up_to_date_databases(tmp_path: Path) -> None:
    """Test _run_update logs info for databases already up to date."""
    mock_logger = MagicMock(spec=logging.Logger)

    mock_result = MagicMock()
    mock_result.edition_id = "GeoLite2-Country"
    mock_result.was_updated = False
    mock_result.new_hash = "abc123"

    mock_updater = MagicMock()
    mock_updater.run = AsyncMock(return_value=[mock_result])
    mock_updater.__aenter__ = AsyncMock(return_value=mock_updater)
    mock_updater.__aexit__ = AsyncMock(return_value=None)

    with patch("geoipupdate_input.Updater", return_value=mock_updater):
        _run_update(
            account_id=TEST_ACCOUNT_ID,
            license_key="key",
            edition_ids=["GeoLite2-Country"],
            database_directory=tmp_path,
            logger=mock_logger,
        )

    mock_logger.info.assert_any_call(
        "%s is up to date (hash: %s)",
        "GeoLite2-Country",
        "abc123",
    )


def test_stream_events_full_flow_downloads_database(
    httpserver: HTTPServer,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Integration test: stream_events downloads a database via HTTP.

    This test exercises the full flow from stream_events through to actually
    downloading and writing a database file, using a mock HTTP server instead
    of mocking the Updater.
    """
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    edition_id = "GeoLite2-Country"
    mmdb_data = _create_test_mmdb()
    mmdb_md5 = hashlib.md5(mmdb_data).hexdigest()  # noqa: S324
    tar_gz_data = _create_tar_gz(mmdb_data, edition_id)

    # Set up metadata endpoint
    httpserver.expect_request(
        "/geoip/updates/metadata",
        query_string=f"edition_id={edition_id}",
    ).respond_with_json(
        {
            "databases": [
                {
                    "edition_id": edition_id,
                    "date": "2024-01-01",
                    "md5": mmdb_md5,
                }
            ]
        }
    )

    # Set up download endpoint
    httpserver.expect_request(
        f"/geoip/databases/{edition_id}/download",
    ).respond_with_data(
        tar_gz_data,
        content_type="application/gzip",
        headers={"Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
    )

    input_obj = GeoIPUpdateInput()

    inputs = MagicMock()
    inputs.metadata = {"session_key": "test_session_key"}

    mock_logger = MagicMock(spec=logging.Logger)

    with (
        patch("geoipupdate_input.get_logger_or_fallback", return_value=mock_logger),
        patch(
            "geoipupdate_input._get_account_credentials",
            return_value=(TEST_ACCOUNT_ID, "test_key"),
        ),
        patch(
            "geoipupdate_input._get_database_names",
            return_value=[edition_id],
        ),
        # Override the host in the Config to point to our test server
        patch(
            "geoipupdate_input.Config",
            lambda **kwargs: PyGeoIPUpdateConfig(
                **{**kwargs, "host": httpserver.url_for("/")}
            ),
        ),
    ):
        input_obj.stream_events(inputs, None)

    # Verify the database file was actually written
    db_file = tmp_path / f"{edition_id}.mmdb"
    assert db_file.exists(), "Database file should have been created"
    assert db_file.read_bytes() == mmdb_data, "Database content should match"

    # Verify success was logged
    mock_logger.info.assert_any_call("Database update completed successfully")


# --- Utility functions for creating test data ---


def _create_test_mmdb() -> bytes:
    """Create a minimal valid MMDB file for testing.

    Returns:
        Bytes of a minimal MMDB file.

    """
    # This is the smallest valid MMDB file structure
    # Magic bytes + minimal metadata
    return (
        b"\x00" * 16  # Data section (empty)
        + b"\xab\xcd\xefMaxMind.com"  # Metadata marker
        + b"\xe0"  # Map with 0 items (metadata)
    )


def _create_tar_gz(mmdb_data: bytes, edition_id: str) -> bytes:
    """Create a tar.gz archive containing an MMDB file.

    Args:
        mmdb_data: The MMDB file contents.
        edition_id: The database edition ID.

    Returns:
        The tar.gz archive as bytes.

    """
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        # Add directory entry
        dir_info = tarfile.TarInfo(name=f"{edition_id}_20240101")
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)

        # Add MMDB file
        file_info = tarfile.TarInfo(name=f"{edition_id}_20240101/{edition_id}.mmdb")
        file_info.size = len(mmdb_data)
        tar.addfile(file_info, io.BytesIO(mmdb_data))

    tar_buffer.seek(0)
    gz_buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buffer, mode="wb") as gz:
        gz.write(tar_buffer.read())

    return gz_buffer.getvalue()
