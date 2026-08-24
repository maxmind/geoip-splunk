"""Tests for the geoip_utils module."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

# Add the lib directory to the path for testing
repo_root = Path(__file__).parent.parent
lib_dir = repo_root / "geoip" / "package" / "lib"
sys.path.insert(0, str(lib_dir))


def test_solnlib_import_surface() -> None:
    """geoip_utils binds its solnlib names inside a try/except
    ImportError, so a renamed or moved name would silently set
    _HAS_SOLNLIB = False app-wide while every mock-based test kept
    passing. solnlib is installed in the dev venv so this test can check
    the bound names are the real ones. It must not import solnlib
    itself: other test files replace the solnlib entries in sys.modules
    with mocks at collection time."""
    import geoip_utils  # noqa: PLC0415

    # Through Any: mypy objects to the implicit re-exports, but reaching
    # the module attributes as bound is the point of the test. The
    # attributes only exist when the import succeeded.
    utils: Any = geoip_utils
    assert utils.ConfManagerException.__module__ == "solnlib.soln_exceptions"
    assert utils.conf_manager.__name__ == "solnlib.conf_manager"
    assert utils.solnlib_log.__name__ == "solnlib.log"


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


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("GeoIP2-Country", True),
        ("GeoLite2_City", True),
        ("db1", True),
        ("", False),
        ("../etc/passwd", False),
        ("name.mmdb", False),
        ("name with spaces", False),
    ],
)
def test_is_valid_database_name(name: str, valid: bool) -> None:  # noqa: FBT001
    import geoip_utils  # noqa: PLC0415

    assert geoip_utils.is_valid_database_name(name) is valid


def test_fill_missing_event_fields_backfills_the_union() -> None:
    import geoip_utils  # noqa: PLC0415

    events: list[dict[str, Any]] = [{"a": 1}, {"b": 2}, {"a": 3, "c": 4}]
    geoip_utils.fill_missing_event_fields(events)

    assert events == [
        {"a": 1, "b": None, "c": None},
        {"a": None, "b": 2, "c": None},
        {"a": 3, "b": None, "c": 4},
    ]


def test_fill_missing_event_fields_keeps_falsy_values() -> None:
    """setdefault must not clobber a field that is present but falsy."""
    import geoip_utils  # noqa: PLC0415

    events: list[dict[str, Any]] = [{"a": 0, "b": ""}, {"c": None}]
    geoip_utils.fill_missing_event_fields(events)

    assert events == [
        {"a": 0, "b": "", "c": None},
        {"a": None, "b": None, "c": None},
    ]


def test_fill_missing_event_fields_empty_list() -> None:
    import geoip_utils  # noqa: PLC0415

    events: list[dict[str, Any]] = []
    geoip_utils.fill_missing_event_fields(events)

    assert events == []


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


def test_get_setting_returns_the_field_value() -> None:
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get.return_value = {"loglevel": "DEBUG"}

        result = geoip_utils.get_setting("test_session_key", "logging", "loglevel")

    conf.get.assert_called_once_with("logging")
    assert result == "DEBUG"


def test_get_setting_none_when_the_field_is_missing() -> None:
    """A field absent from both default/ and local/ reads as None."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get.return_value = {"other": "1"}

        assert (
            geoip_utils.get_setting("test_session_key", "logging", "loglevel") is None
        )


def test_get_setting_raises_when_the_read_fails() -> None:
    """The shipped default/geoip_settings.conf means the conf and its
    stanzas exist on any healthy install, so a failed read is a fault to
    surface, not a fresh install; the caller decides the fallback."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        manager_mod.ConfManager.return_value.get_conf.side_effect = RuntimeError(
            "splunkd unreachable"
        )

        with pytest.raises(RuntimeError, match="splunkd unreachable"):
            geoip_utils.get_setting("test_session_key", "logging", "loglevel")


def test_get_setting_raises_without_solnlib() -> None:
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=False),
        pytest.raises(RuntimeError, match="solnlib is unavailable"),
    ):
        geoip_utils.get_setting("test_session_key", "logging", "loglevel")


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


def test_has_account_credentials_true_when_both_fields_set() -> None:
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        # The realm makes solnlib return the stanza decrypted, so the
        # values here look like real credentials, not masked ones.
        conf.get.return_value = {
            "account_id": "123456",
            "license_key": "abcdef0123456789",
        }

        result = geoip_utils.has_account_credentials("test_session_key")

    manager_mod.ConfManager.assert_called_once_with(
        "test_session_key",
        "geoip",
        realm="__REST_CREDENTIAL__#geoip#configs/conf-geoip_settings",
    )
    conf.get.assert_called_once_with("account", only_current_app=True)
    assert result is True


@pytest.mark.parametrize(
    "stanza",
    [
        {},
        {"account_id": "123456"},
        {"license_key": "abcdef0123456789"},
        {"account_id": "", "license_key": "abcdef0123456789"},
        # The updater rejects a non-numeric account ID (it does not
        # strip either), so these are not usable credentials even though
        # both fields are set.
        {"account_id": " 123456", "license_key": "abcdef0123456789"},
        {"account_id": "12345a", "license_key": "abcdef0123456789"},
        {"account_id": "123456", "license_key": ""},
        {"account_id": None, "license_key": "abcdef0123456789"},
    ],
)
def test_has_account_credentials_false_when_a_field_is_missing_or_invalid(
    stanza: dict[str, object],
) -> None:
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        conf = manager_mod.ConfManager.return_value.get_conf.return_value
        conf.get.return_value = stanza

        assert geoip_utils.has_account_credentials("test_session_key") is False


def test_has_account_credentials_raises_when_the_read_fails() -> None:
    """The shipped default/geoip_settings.conf carries an empty account
    stanza, so a failed read means something is broken, not a fresh
    install; the caller decides the fallback."""
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=True),
        patch.object(geoip_utils, "conf_manager", create=True) as manager_mod,
    ):
        manager_mod.ConfManager.return_value.get_conf.side_effect = RuntimeError(
            "splunkd unreachable"
        )

        with pytest.raises(RuntimeError, match="splunkd unreachable"):
            geoip_utils.has_account_credentials("test_session_key")


def test_has_account_credentials_raises_without_solnlib() -> None:
    import geoip_utils  # noqa: PLC0415

    with (
        patch.object(geoip_utils, "_HAS_SOLNLIB", new=False),
        pytest.raises(RuntimeError, match="solnlib is unavailable"),
    ):
        geoip_utils.has_account_credentials("test_session_key")


def test_validate_account_credentials_accepts_the_updater_form() -> None:
    import geoip_utils  # noqa: PLC0415

    result = geoip_utils.validate_account_credentials("123456", "abcdef0123456789")

    assert result == (123456, "abcdef0123456789")


@pytest.mark.parametrize(
    ("account_id", "license_key"),
    [
        (None, "abcdef0123456789"),
        ("", "abcdef0123456789"),
        ("123456", None),
        ("123456", ""),
    ],
)
def test_validate_account_credentials_rejects_missing_values(
    account_id: str | None,
    license_key: str | None,
) -> None:
    import geoip_utils  # noqa: PLC0415

    with pytest.raises(ValueError, match="not configured"):
        geoip_utils.validate_account_credentials(account_id, license_key)


@pytest.mark.parametrize("account_id", ["12345a", " 123", "1.5", "-1"])
def test_validate_account_credentials_rejects_a_non_numeric_id(
    account_id: str,
) -> None:
    """No leniency the updater does not have: it does not strip, so a
    padded account ID fails every update and must fail here too."""
    import geoip_utils  # noqa: PLC0415

    with pytest.raises(ValueError, match="must be a number"):
        geoip_utils.validate_account_credentials(account_id, "abcdef0123456789")


def test_get_replication_marker_path_with_env_override(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOIP_LOOKUPS_DIR", str(tmp_path))

    import geoip_utils  # noqa: PLC0415

    result = geoip_utils.get_replication_marker_path()
    assert result == tmp_path / "geoip_replication_state.csv"


def test_get_replication_marker_path_default(monkeypatch: MonkeyPatch) -> None:
    """The default is the app's lookups/ directory: it is in Splunk's
    default bundle replication allowlist, which is what lets a marker
    change alter the bundle checksum."""
    monkeypatch.delenv("GEOIP_LOOKUPS_DIR", raising=False)

    import geoip_utils  # noqa: PLC0415

    result = geoip_utils.get_replication_marker_path()
    assert result == (lib_dir.parent / "lookups").resolve() / (
        "geoip_replication_state.csv"
    )


def _marker_path() -> Path:
    import geoip_utils  # noqa: PLC0415

    return geoip_utils.get_replication_marker_path()


@pytest.mark.parametrize(
    ("run_on_indexers", "expected"),
    [
        (True, "run_on_indexers\n1\n"),
        (False, "run_on_indexers\n0\n"),
    ],
)
def test_sync_replication_marker_writes_the_state(
    run_on_indexers: bool,  # noqa: FBT001
    expected: str,
) -> None:
    """Creates the lookups directory and the marker on first sync. The
    content is a valid one-column CSV, since the file lives in lookups/."""
    import geoip_utils  # noqa: PLC0415

    geoip_utils.sync_replication_marker(
        "test_session_key", run_on_indexers=run_on_indexers
    )

    assert _marker_path().read_text(encoding="ascii") == expected


def test_sync_replication_marker_is_a_noop_when_the_state_matches() -> None:
    """An unchanged marker must keep its mtime: any rewrite gives the next
    knowledge bundle a new checksum, and the input syncs hourly, so a
    rewrite here would rebuild the bundle on every peer every hour."""
    import geoip_utils  # noqa: PLC0415

    geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)
    before = _marker_path().stat()

    geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)

    after = _marker_path().stat()
    assert (after.st_mtime_ns, after.st_ino) == (before.st_mtime_ns, before.st_ino)


def test_sync_replication_marker_steady_state_builds_no_logger() -> None:
    """The geoip command syncs on every search head search, and the
    logger lookup costs a REST read, so the matching-marker no-op must
    not build a logger at all."""
    import geoip_utils  # noqa: PLC0415

    geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)

    with patch.object(geoip_utils, "get_logger_or_fallback") as lookup_mock:
        geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)

    lookup_mock.assert_not_called()


def test_sync_replication_marker_rewrites_on_a_state_change() -> None:
    import geoip_utils  # noqa: PLC0415

    geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)
    geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=False)

    assert _marker_path().read_text(encoding="ascii") == "run_on_indexers\n0\n"


def test_sync_replication_marker_rewrites_a_corrupt_marker() -> None:
    """A hand-edited or torn marker must not wedge the sync: unreadable or
    unexpected content means (re)write, not raise."""
    import geoip_utils  # noqa: PLC0415

    _marker_path().parent.mkdir(parents=True, exist_ok=True)
    _marker_path().write_bytes(b"\xff\xfe garbage")

    geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)

    assert _marker_path().read_text(encoding="ascii") == "run_on_indexers\n1\n"


def test_sync_replication_marker_survives_a_raising_success_log() -> None:
    """Never raises covers the success log too: two callers (the settings
    handler after save() has committed, the geoip command's prepare())
    depend on that, and a raise from the logger after the marker was
    written would take them down over a log line."""
    import geoip_utils  # noqa: PLC0415

    logger = MagicMock()
    logger.info.side_effect = RuntimeError("logging broken")

    with patch.object(geoip_utils, "get_logger_or_fallback", return_value=logger):
        geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)

    assert _marker_path().read_text(encoding="ascii") == "run_on_indexers\n1\n"
    logger.exception.assert_called_once()


def test_sync_replication_marker_never_raises(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A failed marker write must not take down a settings save or an
    update run. Pointing the lookups directory inside a file makes both
    the read and the mkdir fail."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("GEOIP_LOOKUPS_DIR", str(blocker / "lookups"))
    logger = MagicMock()

    import geoip_utils  # noqa: PLC0415

    with patch.object(geoip_utils, "get_logger_or_fallback", return_value=logger):
        geoip_utils.sync_replication_marker("test_session_key", run_on_indexers=True)

    logger.exception.assert_called_once()


def test_get_fallback_logger_writes_records_exactly_once() -> None:
    """The fallback logger exists for nodes where conf reads are broken.
    It needs a handler of its own (the REST handler processes give the
    root logger only a NullHandler, so propagated records vanish there)
    and must not also propagate (search-command processes give the root
    logger a stderr handler, so propagated records print twice there).
    It must also not stack a new handler per call: several modules call
    it repeatedly."""
    import geoip_utils  # noqa: PLC0415

    logger = geoip_utils.get_fallback_logger()
    # A copy, since a repeated call must be compared against a snapshot,
    # not against the same live list (pytest's caplog can add handlers of
    # its own, so an exact count would be fragile).
    handlers_after_first = list(logger.handlers)
    geoip_utils.get_fallback_logger()

    assert handlers_after_first
    assert logger.handlers == handlers_after_first
    assert logger.propagate is False


def test_get_logger_or_fallback_returns_the_configured_logger() -> None:
    import geoip_utils  # noqa: PLC0415

    configured = MagicMock()
    with patch.object(geoip_utils, "get_logger", return_value=configured):
        assert geoip_utils.get_logger_or_fallback("test_session_key") is configured


def test_get_logger_or_fallback_never_raises() -> None:
    """get_logger reads its log level over REST, so on a node where conf
    reads fail it raises; every never-fail path (search prepare, settings
    saves, update runs, diagnostics) leans on this guard instead of
    re-implementing it."""
    import geoip_utils  # noqa: PLC0415

    with patch.object(
        geoip_utils,
        "get_logger",
        side_effect=RuntimeError("splunkd unreachable"),
    ):
        logger = geoip_utils.get_logger_or_fallback("test_session_key")

    assert logger is geoip_utils.get_fallback_logger()


def test_get_logger_or_fallback_attempts_a_failing_lookup_only_once() -> None:
    """get_logger's own lru_cache does not cache exceptions, so without a
    cache here every call on a broken node re-attempts the REST read and
    logs another traceback - once per event in the geoip command's
    stream(), so a chunk of unmatched IPs would produce N of each."""
    import geoip_utils  # noqa: PLC0415

    with patch.object(
        geoip_utils,
        "get_logger",
        side_effect=RuntimeError("splunkd unreachable"),
    ) as get_logger_mock:
        first = geoip_utils.get_logger_or_fallback("test_session_key")
        second = geoip_utils.get_logger_or_fallback("test_session_key")

    get_logger_mock.assert_called_once()
    assert second is first
