"""Tests for the searchbnf.conf that UCC generates from globalConfig.json.

UCC generates a searchbnf.conf stanza from the help keys of every command
that sets requiredSearchAssistant. A command without the flag ships with no
help in the Splunk Web search bar, so every command must set it. The tests
render the file with the installed UCC, so a UCC change to the template
fails here too. UCC's schema already checks the syntax length and the
example keys when it builds.
"""

import configparser
import re

from splunk_add_on_ucc_framework.generators.conf_files import SearchbnfConf
from splunk_add_on_ucc_framework.global_config import GlobalConfig

from tests.global_config import GLOBAL_CONFIG_PATH, load_custom_search_commands


def test_every_command_has_a_stanza() -> None:
    parser = _render_searchbnf_conf()
    expected = [f"{c['commandName']}-command" for c in load_custom_search_commands()]
    assert sorted(parser.sections()) == sorted(expected)


def test_every_stanza_has_the_help_keys() -> None:
    parser = _render_searchbnf_conf()
    for command in load_custom_search_commands():
        name = command["commandName"]
        stanza = parser[f"{name}-command"]
        for key in (
            "syntax",
            "description",
            "shortdesc",
            "tags",
            "example1",
            "comment1",
        ):
            assert stanza.get(key), f"{name}: missing {key}"
        assert stanza["usage"] == "public", name


def test_every_syntax_matches_its_command() -> None:
    parser = _render_searchbnf_conf()
    for command in load_custom_search_commands():
        name = command["commandName"]
        syntax = parser[f"{name}-command"]["syntax"]
        assert syntax.split()[0] == name, name
        # Square brackets are literal in searchbnf. Use (<term>)? instead.
        assert "[" not in syntax, name
        arguments = {argument["name"] for argument in command["arguments"]}
        assert set(re.findall(r"(\w+)=", syntax)) == arguments, name
        optional = {a["name"] for a in command["arguments"] if not a.get("required")}
        assert set(re.findall(r"\((\w+)=[^)]*\)\?", syntax)) == optional, name


def _render_searchbnf_conf() -> configparser.ConfigParser:
    global_config = GlobalConfig.from_file(str(GLOBAL_CONFIG_PATH))
    generated = SearchbnfConf(global_config, "unused", "unused").generate()
    assert generated is not None
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(generated[0]["content"])
    return parser
