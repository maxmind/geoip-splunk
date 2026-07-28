"""Tests for the geoip_utils module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

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


def _set_up_migration_dirs(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> tuple[Path, Path]:
    """Point SPLUNK_HOME and MAXMIND_DB_DIR at tmp_path and return the
    legacy (created) and new (not created) database directories."""
    monkeypatch.setenv("SPLUNK_HOME", str(tmp_path / "splunk"))
    legacy_dir = tmp_path / "splunk" / "etc" / "apps" / "geoip" / "local" / "data"
    legacy_dir.mkdir(parents=True)
    new_dir = tmp_path / "databases"
    monkeypatch.setenv("MAXMIND_DB_DIR", str(new_dir))
    return legacy_dir, new_dir


def test_migrate_legacy_databases_moves_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "GeoIP2-Country.mmdb").write_bytes(b"country")
    (legacy_dir / "GeoIP2-ASN.mmdb").write_bytes(b"asn")

    geoip_utils.migrate_legacy_databases(MagicMock())

    assert (new_dir / "GeoIP2-Country.mmdb").read_bytes() == b"country"
    assert (new_dir / "GeoIP2-ASN.mmdb").read_bytes() == b"asn"
    assert not legacy_dir.exists()


def test_migrate_legacy_databases_noop_without_legacy_dir(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import geoip_utils  # noqa: PLC0415

    monkeypatch.setenv("SPLUNK_HOME", str(tmp_path / "splunk"))
    new_dir = tmp_path / "databases"
    monkeypatch.setenv("MAXMIND_DB_DIR", str(new_dir))
    logger = MagicMock()

    geoip_utils.migrate_legacy_databases(logger)

    assert not new_dir.exists()
    logger.info.assert_not_called()
    logger.exception.assert_not_called()


def test_migrate_legacy_databases_does_not_overwrite_newer_download(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A database in both places means the updater already downloaded a
    fresher copy; the legacy file is deleted, never moved over it."""
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "GeoIP2-Country.mmdb").write_bytes(b"stale")
    new_dir.mkdir()
    (new_dir / "GeoIP2-Country.mmdb").write_bytes(b"fresh")

    geoip_utils.migrate_legacy_databases(MagicMock())

    assert (new_dir / "GeoIP2-Country.mmdb").read_bytes() == b"fresh"
    assert not legacy_dir.exists()


def test_migrate_legacy_databases_removes_updater_scratch_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import geoip_utils  # noqa: PLC0415

    legacy_dir, _ = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "tmp123abc.temporary").write_bytes(b"partial download")
    (legacy_dir / ".geoipupdate.lock").write_bytes(b"")

    geoip_utils.migrate_legacy_databases(MagicMock())

    assert not legacy_dir.exists()


def test_migrate_legacy_databases_keeps_unexpected_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "GeoIP2-Country.mmdb").write_bytes(b"country")
    (legacy_dir / "notes.txt").write_bytes(b"not ours to delete")
    logger = MagicMock()

    geoip_utils.migrate_legacy_databases(logger)

    assert (new_dir / "GeoIP2-Country.mmdb").read_bytes() == b"country"
    assert (legacy_dir / "notes.txt").exists()
    logger.exception.assert_not_called()


def test_migrate_legacy_databases_never_raises(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """The destination being uncreatable (a file in the way) must log,
    not propagate: migration runs inside searches and update runs."""
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "GeoIP2-Country.mmdb").write_bytes(b"country")
    new_dir.write_bytes(b"a file where the directory should be")
    logger = MagicMock()

    geoip_utils.migrate_legacy_databases(logger)

    logger.exception.assert_called_once()


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
