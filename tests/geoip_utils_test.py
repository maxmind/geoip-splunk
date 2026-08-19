"""Tests for the geoip_utils module."""

from __future__ import annotations

import errno
import os
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
    # The leftovers keep the legacy directory in replication summaries, so
    # they are named rather than passed over in silence.
    logger.warning.assert_called_once()
    assert "notes.txt" in logger.warning.call_args.args


def test_migrate_legacy_databases_skips_a_vanished_database_quietly(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A source that disappeared mid-migration means another process moved
    it first, which is expected and not worth a warning."""
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "GeoIP2-ASN.mmdb").write_bytes(b"asn")
    (legacy_dir / "GeoIP2-Country.mmdb").write_bytes(b"country")
    logger = MagicMock()
    real_link = os.link

    def link(src: str, dst: str) -> None:
        if Path(src).name == "GeoIP2-ASN.mmdb":
            Path(src).unlink()
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", src)
        real_link(src, dst)

    with patch("geoip_utils.os.link", side_effect=link):
        geoip_utils.migrate_legacy_databases(logger)

    assert (new_dir / "GeoIP2-Country.mmdb").read_bytes() == b"country"
    logger.warning.assert_not_called()
    logger.exception.assert_not_called()


def test_migrate_legacy_databases_warns_when_the_destination_is_gone(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """ENOENT with the source still in place is not the concurrent-migration
    case: without a warning every database would be skipped silently."""
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    (legacy_dir / "GeoIP2-ASN.mmdb").write_bytes(b"asn")
    (legacy_dir / "GeoIP2-Country.mmdb").write_bytes(b"country")
    logger = MagicMock()
    real_link = os.link

    def link(src: str, dst: str) -> None:
        if Path(src).name == "GeoIP2-ASN.mmdb":
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", dst)
        real_link(src, dst)

    with patch("geoip_utils.os.link", side_effect=link):
        geoip_utils.migrate_legacy_databases(logger)

    assert any(
        "Could not migrate" in call.args[0] for call in logger.warning.call_args_list
    )
    # The one failure must not cost the other database its migration.
    assert (new_dir / "GeoIP2-Country.mmdb").read_bytes() == b"country"
    assert (legacy_dir / "GeoIP2-ASN.mmdb").read_bytes() == b"asn"


def test_migrate_legacy_databases_continues_past_an_unmigratable_file(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """One file that cannot be linked must not abandon the rest: sorted()
    fixes the order, so the same file would block them on every run."""
    import geoip_utils  # noqa: PLC0415

    legacy_dir, new_dir = _set_up_migration_dirs(tmp_path, monkeypatch)
    for name in ("A-first", "B-second", "C-third"):
        (legacy_dir / f"{name}.mmdb").write_bytes(name.encode())
    logger = MagicMock()
    real_link = os.link

    def link(src: str, dst: str) -> None:
        if Path(src).name == "A-first.mmdb":
            raise PermissionError(errno.EPERM, "Operation not permitted", src)
        real_link(src, dst)

    with patch("geoip_utils.os.link", side_effect=link):
        geoip_utils.migrate_legacy_databases(logger)

    assert (new_dir / "B-second.mmdb").read_bytes() == b"B-second"
    assert (new_dir / "C-third.mmdb").read_bytes() == b"C-third"
    assert (legacy_dir / "A-first.mmdb").exists()
    logger.exception.assert_called_once()


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


def test_get_configured_database_names_reads_from_the_geoip_namespace() -> None:
    """The read must pin app_name to the geoip app, like the other
    conf reads in this module."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get_all.return_value = {
            "GeoLite2-Country": {},
            "GeoLite2-City": {},
        }

        result = geoip_utils.get_configured_database_names("test_session_key")

    manager_mod.ConfManager.assert_called_once_with("test_session_key", "geoip")
    manager_mod.ConfManager.return_value.get_conf.assert_called_once_with(
        "geoip_databases"
    )
    conf.get_all.assert_called_once_with(only_current_app=True)
    assert result == ["GeoLite2-Country", "GeoLite2-City"]


def test_get_configured_database_names_excludes_default_stanza() -> None:
    """The 'default' stanza is conf plumbing, not a configured database."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get_all.return_value = {
            "default": {},
            "GeoLite2-Country": {},
        }

        result = geoip_utils.get_configured_database_names("test_session_key")

    assert result == ["GeoLite2-Country"]


def test_get_configured_database_names_returns_empty_list() -> None:
    """No configured databases is not an error here; callers decide."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get_all.return_value = {"default": {}}

        result = geoip_utils.get_configured_database_names("test_session_key")

    assert result == []


def test_get_configured_database_names_empty_when_the_conf_is_missing() -> None:
    """The conf file only exists once the first database is added, so a
    missing file means nothing is configured, not an error."""
    import geoip_utils  # noqa: PLC0415

    class ManagerError(Exception):
        pass

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
        patch.object(
            geoip_utils,
            "ConfManagerException",
            new=ManagerError,
            create=True,
        ),
    ):
        manager_mod.ConfManager.return_value.get_conf.side_effect = ManagerError(
            "Config file not found"
        )

        result = geoip_utils.get_configured_database_names("test_session_key")

    assert result == []


def test_get_configured_database_names_raises_without_solnlib() -> None:
    """On an indexer solnlib is absent; the caller's fallback handles it."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=False),
        pytest.raises(RuntimeError, match="solnlib is unavailable"),
    ):
        geoip_utils.get_configured_database_names("test_session_key")
