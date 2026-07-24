"""Tests for the geoip_utils module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

# Add the lib directory to the path for testing
repo_root = Path(__file__).parent.parent
lib_dir = repo_root / "geoip" / "package" / "lib"
sys.path.insert(0, str(lib_dir))


def test_get_database_directory_with_env_override(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that MAXMIND_DB_DIR env var overrides the default directory."""
    monkeypatch.setenv("MAXMIND_DB_DIR", str(tmp_path))

    import geoip_utils  # noqa: PLC0415

    result = geoip_utils.get_database_directory()
    assert result == tmp_path


def test_get_database_directory_default(monkeypatch: MonkeyPatch) -> None:
    """Test the default database directory path."""
    monkeypatch.delenv("MAXMIND_DB_DIR", raising=False)

    import geoip_utils  # noqa: PLC0415

    result = geoip_utils.get_database_directory()
    assert result == (lib_dir.parent / "databases").resolve()


def test_is_truthy() -> None:
    import geoip_utils  # noqa: PLC0415

    assert geoip_utils.is_truthy("1")
    assert geoip_utils.is_truthy(1)
    assert geoip_utils.is_truthy("TRUE")
    assert geoip_utils.is_truthy(" yes ")
    assert not geoip_utils.is_truthy("0")
    assert not geoip_utils.is_truthy("false")
    assert not geoip_utils.is_truthy(None)


def test_get_run_on_indexers_setting_reads_from_the_geoip_namespace() -> None:
    """The read must pin app_name to the geoip app: the command can be
    dispatched from any app, and the dispatching app's namespace only
    resolves this conf via the app's export = system metadata."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get.return_value = {geoip_utils.RUN_ON_INDEXERS_FIELD: "1"}

        result = geoip_utils.get_run_on_indexers_setting("test_session_key")

    manager_mod.ConfManager.assert_called_once_with("test_session_key", "geoip")
    manager_mod.ConfManager.return_value.get_conf.assert_called_once_with(
        "geoip_settings"
    )
    conf.get.assert_called_once_with(geoip_utils.DISTRIBUTION_STANZA)
    assert result == "1"


def test_get_run_on_indexers_setting_raises_without_solnlib() -> None:
    """On an indexer solnlib is absent; the caller's fallback handles it."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=False),
        pytest.raises(RuntimeError, match="solnlib is unavailable"),
    ):
        geoip_utils.get_run_on_indexers_setting("test_session_key")
