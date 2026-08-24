"""Tests for geoip/package/default/distsearch.conf.

The indexer execution toggle (geoip_rh_settings.py) overrides the
[replicationAllowlist] geoip_mmdb key in local/distsearch.conf, so the
shipped default and the constants in geoip_utils.py must stay in sync.
"""

import configparser
import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "geoip" / "package" / "lib"))

import geoip_utils  # noqa: E402

_DISTSEARCH_CONF = repo_root / "geoip" / "package" / "default" / "distsearch.conf"


def _load() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(_DISTSEARCH_CONF)
    return parser


def test_mmdb_key_defaults_to_the_allow_nothing_pattern() -> None:
    """Indexer execution is opt-in: the shipped default must not let the
    databases ride the knowledge bundle."""
    allowlist = _load()[geoip_utils.REPLICATION_ALLOWLIST_STANZA]
    assert (
        allowlist[geoip_utils.MMDB_ALLOWLIST_KEY]
        == geoip_utils.MMDB_ALLOW_NOTHING_PATTERN
    )


def test_allow_pattern_matches_only_database_files() -> None:
    """The pattern the toggle writes when enabled. The dots must stay
    unescaped: in Splunk's pattern language a dot is literal, and \\. makes
    the pattern match nothing at all (see "Splunk path patterns in conf
    files" in CLAUDE.md)."""
    assert geoip_utils.MMDB_ALLOW_PATTERN == "apps/geoip/databases/*.mmdb"


def test_allow_nothing_pattern_never_matches_a_database() -> None:
    assert geoip_utils.MMDB_ALLOW_NOTHING_PATTERN.startswith("apps/geoip/databases/")
    assert not geoip_utils.MMDB_ALLOW_NOTHING_PATTERN.endswith(".mmdb")


def test_allowlist_covers_the_runtime_libs_and_toggle_key_only() -> None:
    """The geoip command's imports on an indexer plus the databases' toggle
    key, and nothing more.

    Keeping the library list minimal keeps the large download-only
    dependencies (grpc, aiohttp, opentelemetry, ...) out of the knowledge
    bundle.
    """
    allowlist = _load()[geoip_utils.REPLICATION_ALLOWLIST_STANZA]
    assert dict(allowlist) == {
        "geoip_lib_geoip_utils": "apps/geoip/lib/geoip_utils.py",
        "geoip_lib_splunklib": "apps/geoip/lib/splunklib/...",
        # maxminddb* includes the dist-info directory, which maxminddb
        # reads at import time
        "geoip_lib_maxminddb": "apps/geoip/lib/maxminddb*/...",
        geoip_utils.MMDB_ALLOWLIST_KEY: geoip_utils.MMDB_ALLOW_NOTHING_PATTERN,
    }


def test_no_denylist_stanza() -> None:
    """Nothing needs denying: the app's databases/ directory (the databases,
    the updater's in-progress *.temporary downloads, its lock file) is
    outside Splunk's default allowlist, so none of it can ride the knowledge
    bundle in the first place. The one file the app writes inside the
    allowlist - the lookups/ bundle state marker - is meant to ride the
    bundle."""
    assert not _load().has_section("replicationDenylist")
