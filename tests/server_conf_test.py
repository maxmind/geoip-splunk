"""Tests for geoip/package/default/server.conf.

Shipping a server.conf in the package suppresses UCC's generated one
(UCC's create_server_conf.py only generates the file when the source
package does not contain it), so the conf_replication_include lines UCC
would have generated must be maintained by hand. These tests catch drift.
"""

import configparser
from pathlib import Path

_SERVER_CONF = (
    Path(__file__).parent.parent / "geoip" / "package" / "default" / "server.conf"
)


def _load_shclustering() -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read(_SERVER_CONF)
    return dict(parser["shclustering"])


def test_replicates_ucc_generated_conf_includes() -> None:
    """The lines UCC would have generated for the app's custom confs."""
    stanza = _load_shclustering()
    assert stanza["conf_replication_include.geoip_settings"] == "true"
    assert stanza["conf_replication_include.geoip_databases"] == "true"


def test_replicates_distsearch_conf() -> None:
    """The indexer execution toggle's distsearch override must reach all
    search head cluster members."""
    stanza = _load_shclustering()
    assert stanza["conf_replication_include.distsearch"] == "true"


def test_only_conf_replication_include_settings() -> None:
    """AppInspect (cloud tag) rejects other [shclustering] settings - such
    as the conf_replication_summary excludelist entries the databases would
    need if they lived in a directory SHC replication summaries capture.
    They live in databases/, which the summaries never capture, so no other
    settings are needed."""
    stanza = _load_shclustering()
    unexpected = [k for k in stanza if not k.startswith("conf_replication_include.")]
    assert not unexpected
