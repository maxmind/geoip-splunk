"""Tests for the geoip_handler module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# Mock solnlib and splunktaucclib before importing the handler modules
mock_conf_manager = MagicMock()
mock_solnlib = MagicMock()
mock_solnlib.conf_manager = mock_conf_manager
sys.modules["solnlib"] = mock_solnlib
sys.modules["solnlib.conf_manager"] = mock_conf_manager

mock_admin_external = MagicMock()
mock_rest_handler = MagicMock()
mock_rest_handler.admin_external = mock_admin_external
mock_splunktaucclib = MagicMock()
mock_splunktaucclib.rest_handler = mock_rest_handler
mock_splunktaucclib.rest_handler.admin_external = mock_admin_external
mock_splunktaucclib.rest_handler.admin_external.AdminExternalHandler = MagicMock
sys.modules["splunktaucclib"] = mock_splunktaucclib
sys.modules["splunktaucclib.rest_handler"] = mock_rest_handler
sys.modules["splunktaucclib.rest_handler.admin_external"] = mock_admin_external

from geoip_handler import (  # noqa: E402  # type: ignore[import-not-found]
    _run_update_background,
    trigger_background_update,
)


def test_run_update_background_calls_run_database_update() -> None:
    """Test that _run_update_background calls run_database_update with correct args."""
    with patch("geoipupdate_input.run_database_update") as mock_run:
        _run_update_background("test_session_key")

    mock_run.assert_called_once_with("test_session_key")


def test_trigger_background_update_spawns_thread() -> None:
    """Test that trigger_background_update spawns a non-daemon thread."""
    with patch("geoip_handler.threading.Thread") as mock_thread_class:
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        trigger_background_update("test_session_key")

        mock_thread_class.assert_called_once_with(
            target=_run_update_background,
            args=("test_session_key",),
            daemon=False,
        )
        mock_thread.start.assert_called_once()
