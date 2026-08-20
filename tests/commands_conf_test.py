"""Tests for geoip/package/default/commands.conf.

UCC generates a commands.conf stanza for every command in
globalConfig.json, but then replaces the whole generated file with the
shipped one. A command missing from the shipped file is therefore
silently unregistered, so the two files must stay in sync.
"""

import configparser
import json
from pathlib import Path

repo_root = Path(__file__).parent.parent

_COMMANDS_CONF = repo_root / "geoip" / "package" / "default" / "commands.conf"
_GLOBAL_CONFIG = repo_root / "geoip" / "globalConfig.json"


def _load_commands_conf() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(_COMMANDS_CONF)
    return parser


def _load_command_names() -> list[str]:
    global_config = json.loads(_GLOBAL_CONFIG.read_text())
    return [command["commandName"] for command in global_config["customSearchCommand"]]


def test_every_command_has_a_stanza() -> None:
    parser = _load_commands_conf()
    assert sorted(parser.sections()) == sorted(_load_command_names())


def test_every_stanza_has_the_required_settings() -> None:
    parser = _load_commands_conf()
    for name in _load_command_names():
        stanza = parser[name]
        # The filename is the UCC-generated wrapper, not the source file
        # named in globalConfig.json.
        assert stanza["filename"] == f"{name}.py"
        # Streaming and generating commands using the Splunk SDK need SCP2.
        assert stanza["chunked"] == "true"
        assert stanza["python.version"] == "python3"
        assert stanza["python.required"] == "3.13"
