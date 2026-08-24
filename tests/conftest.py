import os
import sys
from pathlib import Path

import pytest

# Set the test database directory before importing maxmind_command
repo_root = Path(__file__).parent.parent
test_db_dir = repo_root / "tests" / "data" / "test-data"
os.environ["MAXMIND_DB_DIR"] = str(test_db_dir)

# Add the package bin and lib directories to the path
bin_dir = repo_root / "geoip" / "package" / "bin"
lib_dir = repo_root / "geoip" / "package" / "lib"
sys.path.insert(0, str(bin_dir))
sys.path.insert(0, str(lib_dir))

import geoip_command  # noqa: E402  (needs the sys.path setup above)
import geoip_utils  # noqa: E402  (needs the sys.path setup above)


@pytest.fixture(autouse=True)
def _force_solnlib_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in the no-solnlib fallback mode.

    solnlib is installed in the dev venv so that the import-surface test
    can verify geoip_utils binds the real names (its try/except
    ImportError would otherwise silently absorb a renamed class). But no
    splunkd runs here, so any test that reached a solnlib code path
    unpatched would try REST against localhost. Tests that exercise
    solnlib paths patch _HAS_SOLNLIB (and conf_manager) themselves.
    """
    monkeypatch.setattr(geoip_utils, "_HAS_SOLNLIB", False)


@pytest.fixture(autouse=True)
def _isolate_splunk_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point SPLUNK_HOME at a per-test tmp_path.

    migrate_legacy_databases resolves its source directory via
    SPLUNK_HOME (default /opt/splunk), and several tests reach it
    through _get_reader and run_database_update. Without isolation,
    running the suite on a machine with the app installed would move
    the real databases out of the installed app. Tests that need their
    own SPLUNK_HOME set it with monkeypatch, which overrides this.
    """
    monkeypatch.setenv("SPLUNK_HOME", str(tmp_path / "splunk"))


@pytest.fixture(autouse=True)
def _isolate_lookups_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the bundle state marker at a per-test tmp_path.

    get_replication_marker_path resolves the marker path relative to
    geoip_utils.py, which in the suite is the repo's package tree; without
    isolation, tests reaching the marker sync (through the settings
    handler or run_database_update) would create
    geoip/package/lookups/geoip_replication_state.csv in the repo.
    """
    monkeypatch.setenv("GEOIP_LOOKUPS_DIR", str(tmp_path / "lookups"))


@pytest.fixture(autouse=True)
def _clear_logger_caches() -> None:
    """Empty the lru_caches on geoip_utils' logger lookups.

    Both caches live as long as the process and are keyed by the session
    key, which is the same mock value across most tests. Without
    clearing, a test that builds a logger leaves it cached, and a later
    test patching geoip_utils.get_logger with a side_effect would get
    the cached logger instead - its broken-logger path silently never
    exercised, passing or failing on execution order.
    """
    geoip_utils.get_logger.cache_clear()
    geoip_utils.get_logger_or_fallback.cache_clear()


@pytest.fixture(autouse=True)
def _clear_reader_cache() -> None:
    """Empty geoip_command's module-level reader cache.

    The cache is keyed by database name only and lives as long as the
    process. In a search that is one process per search, but in the
    suite it is every test at once, so a test that opens a database
    from its own tmp_path leaves a reader behind pointing into a
    directory that is then deleted. The next test to use that name
    would get the stale reader instead of opening its own file, and
    pass or fail depending on execution order.
    """
    geoip_command._readers.clear()
