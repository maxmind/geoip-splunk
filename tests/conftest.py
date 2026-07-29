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
