"""Tests for the geoipupdate_script scripted-input wrapper."""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

# Add the lib and bin directories to the path for testing
repo_root = Path(__file__).parent.parent
lib_dir = repo_root / "geoip" / "package" / "lib"
bin_dir = repo_root / "geoip" / "package" / "bin"
sys.path.insert(0, str(lib_dir))
sys.path.insert(0, str(bin_dir))

# Mock solnlib before importing geoipupdate_script since it imports
# geoipupdate_input, which imports solnlib (only in the app's runtime deps)
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

# Now we can import geoipupdate_script since solnlib is mocked
import geoipupdate_script  # noqa: E402  # type: ignore[import-not-found]


def test_main_runs_update_with_session_key(monkeypatch: MonkeyPatch) -> None:
    """Test that main reads the session key from stdin and runs the update."""
    mock_run = MagicMock()
    mock_logger = MagicMock(spec=logging.Logger)
    monkeypatch.setattr(geoipupdate_script, "run_database_update", mock_run)
    monkeypatch.setattr(
        geoipupdate_script,
        "get_logger",
        MagicMock(return_value=mock_logger),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("abc123\n"))

    geoipupdate_script.main()

    mock_run.assert_called_once_with("abc123")
    # The wrapper logs that the scripted input (not the modular input) ran.
    mock_logger.info.assert_called_once()


def test_main_skips_update_with_empty_stdin(monkeypatch: MonkeyPatch) -> None:
    """Test that main skips the update and logs when stdin is empty."""
    mock_run = MagicMock()
    mock_logger = MagicMock(spec=logging.Logger)
    monkeypatch.setattr(geoipupdate_script, "run_database_update", mock_run)
    monkeypatch.setattr(
        geoipupdate_script,
        "get_fallback_logger",
        MagicMock(return_value=mock_logger),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    geoipupdate_script.main()

    mock_run.assert_not_called()
    mock_logger.error.assert_called_once()


def test_main_skips_update_with_whitespace_stdin(monkeypatch: MonkeyPatch) -> None:
    """Test that whitespace-only stdin is treated as an empty session key."""
    mock_run = MagicMock()
    mock_logger = MagicMock(spec=logging.Logger)
    monkeypatch.setattr(geoipupdate_script, "run_database_update", mock_run)
    monkeypatch.setattr(
        geoipupdate_script,
        "get_fallback_logger",
        MagicMock(return_value=mock_logger),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("   \n"))

    geoipupdate_script.main()

    mock_run.assert_not_called()
    mock_logger.error.assert_called_once()
