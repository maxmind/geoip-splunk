"""Tests for the geoip_utils module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

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
