"""Tests for the distribution toggle handling in geoip_rh_settings.py.

The globalConfig.json <-> SETTINGS_FIELD_SPECS drift tests live in
geoip_rh_settings_test.py; these tests cover the handler-side behavior.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Mock solnlib, splunktaucclib, and the UCC-generated import_declare_test
# before importing the handler module
mock_conf_manager = MagicMock()
mock_solnlib = MagicMock()
mock_solnlib.conf_manager = mock_conf_manager
sys.modules["solnlib"] = mock_solnlib
sys.modules["solnlib.conf_manager"] = mock_conf_manager

mock_admin_external = MagicMock()
mock_endpoint = MagicMock()
mock_error = MagicMock()


class FakeRestError(Exception):
    """Stand-in for splunktaucclib's RestError.

    A real exception class is needed so the module under test can raise it.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(status, message)
        self.status = status
        self.message = message


mock_error.RestError = FakeRestError


class FakeAdminExternalHandler:
    """Stand-in base class for splunktaucclib's AdminExternalHandler.

    A real class (rather than MagicMock) so GeoipSettingsHandler can be
    instantiated and its dispatch methods exercised; the base methods it
    chains to are no-ops.
    """

    def handleEdit(self, confInfo: object) -> None:
        pass

    def handleCreate(self, confInfo: object) -> None:
        pass

    def handleRemove(self, confInfo: object) -> None:
        pass


mock_rest_handler = MagicMock()
mock_rest_handler.admin_external = mock_admin_external
mock_rest_handler.endpoint = mock_endpoint
mock_rest_handler.error = mock_error
mock_splunktaucclib = MagicMock()
mock_splunktaucclib.rest_handler = mock_rest_handler
mock_splunktaucclib.rest_handler.admin_external.AdminExternalHandler = (
    FakeAdminExternalHandler
)
sys.modules["splunktaucclib"] = mock_splunktaucclib
sys.modules["splunktaucclib.rest_handler"] = mock_rest_handler
sys.modules["splunktaucclib.rest_handler.admin_external"] = mock_admin_external
sys.modules["splunktaucclib.rest_handler.endpoint"] = mock_endpoint
sys.modules["splunktaucclib.rest_handler.error"] = mock_error
sys.modules["import_declare_test"] = MagicMock()

import geoip_rh_settings  # noqa: E402  # type: ignore[import-not-found]
from geoip_utils import (  # noqa: E402
    DISTRIBUTION_STANZA,
    MMDB_ALLOW_NOTHING_PATTERN,
    MMDB_ALLOW_PATTERN,
    MMDB_ALLOWLIST_KEY,
    RUN_ON_INDEXERS_FIELD,
)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({RUN_ON_INDEXERS_FIELD: ["1"]}, True),
        ({RUN_ON_INDEXERS_FIELD: ["0"]}, False),
        ({RUN_ON_INDEXERS_FIELD: [None]}, False),
        ({RUN_ON_INDEXERS_FIELD: []}, False),
        ({}, False),
    ],
)
def test_parse_run_on_indexers(
    data: dict[str, Any],
    expected: bool,  # noqa: FBT001
) -> None:
    assert geoip_rh_settings._parse_run_on_indexers(data) is expected


def test_apply_mmdb_replication_enabled_writes_allow_pattern() -> None:
    with patch("geoip_rh_settings.conf_manager.ConfManager") as manager:
        conf = manager.return_value.get_conf.return_value

        geoip_rh_settings._apply_mmdb_replication(
            "test_session_key", run_on_indexers=True
        )

        manager.assert_called_once_with("test_session_key", "geoip")
        manager.return_value.get_conf.assert_called_once_with("distsearch")
        conf.update.assert_called_once_with(
            "replicationAllowlist",
            {MMDB_ALLOWLIST_KEY: MMDB_ALLOW_PATTERN},
        )


def test_apply_mmdb_replication_disabled_restores_allow_nothing_pattern() -> None:
    with patch("geoip_rh_settings.conf_manager.ConfManager") as manager:
        conf = manager.return_value.get_conf.return_value

        geoip_rh_settings._apply_mmdb_replication(
            "test_session_key", run_on_indexers=False
        )

        conf.update.assert_called_once_with(
            "replicationAllowlist",
            {MMDB_ALLOWLIST_KEY: MMDB_ALLOW_NOTHING_PATTERN},
        )


@pytest.mark.parametrize(
    ("run_on_indexers", "expected_fragment"),
    [
        # The messages reflect _save_distribution's write order: enabling
        # writes distsearch before the setting, disabling after.
        (True, "the setting was not saved"),
        (False, "The setting was saved"),
    ],
)
def test_apply_mmdb_replication_write_failure_raises_rest_error(
    run_on_indexers: bool,  # noqa: FBT001
    expected_fragment: str,
) -> None:
    with patch("geoip_rh_settings.conf_manager.ConfManager") as manager:
        conf = manager.return_value.get_conf.return_value
        conf.update.side_effect = RuntimeError("splunkd unreachable")

        with pytest.raises(FakeRestError) as exc_info:
            geoip_rh_settings._apply_mmdb_replication(
                "test_session_key", run_on_indexers=run_on_indexers
            )

        internal_server_error = 500
        assert exc_info.value.status == internal_server_error
        assert "distsearch.conf" in exc_info.value.message
        assert expected_fragment in exc_info.value.message


def _make_handler(
    stanza_id: str, data: dict[str, Any]
) -> geoip_rh_settings.GeoipSettingsHandler:
    """Build a GeoipSettingsHandler without running base-class __init__."""
    handler = object.__new__(geoip_rh_settings.GeoipSettingsHandler)
    handler.callerArgs = SimpleNamespace(id=stanza_id, data=data)
    handler.getSessionKey = lambda: "test_session_key"
    return handler


def test_handle_edit_enable_writes_distsearch_before_saving() -> None:
    """A failed distsearch write on enable must leave the setting off:
    committed setting + placeholder allowlist breaks every geoip search
    in a way a restart does not fix."""
    handler = _make_handler(DISTRIBUTION_STANZA, {RUN_ON_INDEXERS_FIELD: ["1"]})
    order = MagicMock()
    with (
        patch.object(geoip_rh_settings, "_apply_mmdb_replication", order.apply),
        patch.object(FakeAdminExternalHandler, "handleEdit", order.save),
    ):
        handler.handleEdit(MagicMock())

    assert [name for name, _, _ in order.mock_calls] == ["apply", "save"]
    order.apply.assert_called_once_with("test_session_key", run_on_indexers=True)


def test_handle_edit_enable_does_not_save_when_distsearch_write_fails() -> None:
    handler = _make_handler(DISTRIBUTION_STANZA, {RUN_ON_INDEXERS_FIELD: ["1"]})
    with (
        patch.object(
            geoip_rh_settings,
            "_apply_mmdb_replication",
            side_effect=FakeRestError(500, "splunkd unreachable"),
        ),
        patch.object(FakeAdminExternalHandler, "handleEdit") as save_mock,
        pytest.raises(FakeRestError),
    ):
        handler.handleEdit(MagicMock())

    save_mock.assert_not_called()


def test_handle_create_disable_saves_before_writing_distsearch() -> None:
    """Disabling is the opposite order: a failed distsearch write then
    leaves only extra replication, not broken searches."""
    handler = _make_handler(DISTRIBUTION_STANZA, {RUN_ON_INDEXERS_FIELD: ["0"]})
    order = MagicMock()
    with (
        patch.object(geoip_rh_settings, "_apply_mmdb_replication", order.apply),
        patch.object(FakeAdminExternalHandler, "handleCreate", order.save),
    ):
        handler.handleCreate(MagicMock())

    assert [name for name, _, _ in order.mock_calls] == ["save", "apply"]
    order.apply.assert_called_once_with("test_session_key", run_on_indexers=False)


def test_handle_edit_account_does_not_touch_distsearch() -> None:
    handler = _make_handler("account", {"account_id": ["123"]})
    with (
        patch.object(geoip_rh_settings, "_apply_mmdb_replication") as apply_mock,
        patch.object(geoip_rh_settings, "trigger_background_update") as update_mock,
    ):
        handler.handleEdit(MagicMock())

    apply_mock.assert_not_called()
    update_mock.assert_called_once_with("test_session_key")


def test_handle_remove_distribution_restores_allow_nothing_pattern() -> None:
    handler = _make_handler(DISTRIBUTION_STANZA, {})
    with patch.object(geoip_rh_settings, "_apply_mmdb_replication") as apply_mock:
        handler.handleRemove(MagicMock())

    apply_mock.assert_called_once_with("test_session_key", run_on_indexers=False)
