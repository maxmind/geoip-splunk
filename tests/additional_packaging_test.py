"""Tests for the UCC post-build hook in geoip/additional_packaging.py."""

import importlib.util
import json
import warnings
from pathlib import Path
from types import ModuleType

import pytest
from splunk_add_on_ucc_framework.generators.python_files.create_custom_command_python import (  # noqa: E501
    CustomCommandPy,
)
from splunk_add_on_ucc_framework.global_config import GlobalConfig

from tests.global_config import GLOBAL_CONFIG_PATH

_MODULE_PATH = Path(__file__).parent.parent / "geoip" / "additional_packaging.py"

# What UCC's custom command templates generate (abbreviated), containing
# all the markers the hook rewrites. UCC copies the syntax and description
# into the class docstring.
_GENERATED_GEOIP_WRAPPER = """\
import sys
import import_declare_test

from splunklib.searchcommands import \\
    dispatch, StreamingCommand, Configuration, Option, validators
from geoip_command import stream

@Configuration()
class GeoipCommand(StreamingCommand):
    \"\"\"

    ##Syntax
    geoip databases=<string>

    ##Description
    Adds MaxMind GeoIP and GeoLite data to events.

    \"\"\"

    databases = Option(name='databases', require=True)

    def stream(self, events):
        return stream(self, events)

dispatch(GeoipCommand, sys.argv, sys.stdin, sys.stdout, __name__)
"""

_GENERATED_GEOIPDEBUG_WRAPPER = """\
import sys
import import_declare_test

from splunklib.searchcommands import \\
    dispatch, GeneratingCommand, Configuration, Option, validators
from geoipdebug_command import generate

@Configuration()
class GeoipdebugCommand(GeneratingCommand):
    \"\"\"

    ##Syntax
    geoipdebug [indexers=<bool>]

    ##Description
    Reports GeoIP database and app diagnostics.

    \"\"\"

    indexers = Option(name='indexers', require=False, \\
        validate=validators.Boolean(), default='false')

    def generate(self):
        return generate(self)

dispatch(GeoipdebugCommand, sys.argv, sys.stdin, sys.stdout, __name__)
"""


def _load_additional_packaging() -> ModuleType:
    spec = importlib.util.spec_from_file_location("additional_packaging", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_wrappers(tmp_path: Path) -> dict[str, Path]:
    (tmp_path / "bin").mkdir()
    wrappers = {}
    for name, content in [
        ("geoip.py", _GENERATED_GEOIP_WRAPPER),
        ("geoipdebug.py", _GENERATED_GEOIPDEBUG_WRAPPER),
    ]:
        wrapper = tmp_path / "bin" / name
        wrapper.write_text(content)
        wrappers[name] = wrapper
    return wrappers


def test_make_command_distribution_toggleable_rewrites_geoip_wrapper(
    tmp_path: Path,
) -> None:
    wrappers = _write_wrappers(tmp_path)

    _load_additional_packaging().make_command_distribution_toggleable(tmp_path)

    result = wrappers["geoip.py"].read_text()
    assert "from geoip_command import prepare, stream" in result
    assert "@Configuration(distributed=False)" in result
    assert (
        "    def prepare(self):\n        prepare(self)\n\n    def stream(self, events):"
    ) in result
    # The rewritten wrapper must still be valid Python.
    compile(result, str(wrappers["geoip.py"]), "exec")


def test_make_command_distribution_toggleable_rewrites_geoipdebug_wrapper(
    tmp_path: Path,
) -> None:
    wrappers = _write_wrappers(tmp_path)

    _load_additional_packaging().make_command_distribution_toggleable(tmp_path)

    result = wrappers["geoipdebug.py"].read_text()
    assert "from geoipdebug_command import generate, prepare" in result
    assert "@Configuration(distributed=False)" in result
    assert (
        "    def prepare(self):\n        prepare(self)\n\n    def generate(self):"
    ) in result
    # The rewritten wrapper must still be valid Python.
    compile(result, str(wrappers["geoipdebug.py"]), "exec")


def test_make_command_distribution_toggleable_rewrites_ucc_wrappers(
    tmp_path: Path,
) -> None:
    """The hook must rewrite the wrappers UCC renders from the real
    globalConfig.json, help text included, into valid Python."""
    global_config = GlobalConfig.from_file(str(GLOBAL_CONFIG_PATH))
    generated = CustomCommandPy(global_config, "unused", "unused").generate()
    assert generated is not None
    (tmp_path / "bin").mkdir()
    for wrapper in generated:
        (tmp_path / "bin" / wrapper["file_name"]).write_text(wrapper["content"])

    _load_additional_packaging().make_command_distribution_toggleable(tmp_path)

    for wrapper in generated:
        path = tmp_path / "bin" / wrapper["file_name"]
        result = path.read_text()
        assert "@Configuration(distributed=False)" in result
        assert "    def prepare(self):\n        prepare(self)\n" in result
        # A backslash in the help text is a SyntaxWarning, and a triple
        # quote is a SyntaxError.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compile(result, str(path), "exec")


# Each replacement keeps the wrapper valid Python, as a real template
# change would: the hook parses the wrapper to find its help docstring.
@pytest.mark.parametrize(
    ("wrapper_name", "marker", "replacement"),
    [
        ("geoip.py", "from geoip_command import stream", "# removed"),
        ("geoip.py", "@Configuration()", "# removed"),
        ("geoip.py", "    def stream(self, events):", "    def run(self, events):"),
        ("geoipdebug.py", "from geoipdebug_command import generate", "# removed"),
        ("geoipdebug.py", "@Configuration()", "# removed"),
        ("geoipdebug.py", "    def generate(self):", "    def run(self):"),
    ],
)
def test_make_command_distribution_toggleable_raises_without_marker(
    tmp_path: Path,
    wrapper_name: str,
    marker: str,
    replacement: str,
) -> None:
    wrappers = _write_wrappers(tmp_path)
    wrapper = wrappers[wrapper_name]
    wrapper.write_text(wrapper.read_text().replace(marker, replacement))

    with pytest.raises(RuntimeError, match="template may have changed"):
        _load_additional_packaging().make_command_distribution_toggleable(tmp_path)


@pytest.mark.parametrize(
    "marker", ["from geoip_command import stream", "@Configuration()"]
)
def test_make_command_distribution_toggleable_ignores_marker_in_help(
    tmp_path: Path,
    marker: str,
) -> None:
    """A marker in the help docstring is neither counted nor rewritten."""
    wrappers = _write_wrappers(tmp_path)
    wrapper = wrappers["geoip.py"]
    help_line = f"    ##Description\n    {marker}\n"
    wrapper.write_text(wrapper.read_text().replace("    ##Description\n", help_line))

    _load_additional_packaging().make_command_distribution_toggleable(tmp_path)

    result = wrapper.read_text()
    assert help_line in result
    assert "@Configuration(distributed=False)\nclass GeoipCommand" in result


def test_make_command_distribution_toggleable_raises_on_marker_only_in_help(
    tmp_path: Path,
) -> None:
    """If the template drops a marker, a copy in the help text must not
    stand in for it."""
    wrappers = _write_wrappers(tmp_path)
    wrapper = wrappers["geoip.py"]
    source = wrapper.read_text().replace("@Configuration()\n", "")
    wrapper.write_text(
        source.replace(
            "    ##Description\n", "    ##Description\n    @Configuration()\n"
        )
    )

    with pytest.raises(RuntimeError, match="template may have changed"):
        _load_additional_packaging().make_command_distribution_toggleable(tmp_path)


def test_make_command_distribution_toggleable_rejects_unknown_command_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A commandType outside the entry-point map must fail the build (with
    KeyError, which UCC's except ImportError does not swallow), never ship
    that command's wrapper without the rewrite."""
    _write_wrappers(tmp_path)
    config = tmp_path / "globalConfig.json"
    config.write_text(
        json.dumps(
            {
                "customSearchCommand": [
                    {
                        "commandName": "geoip",
                        "fileName": "geoip_command.py",
                        "commandType": "reporting",
                    }
                ]
            }
        )
    )
    module = _load_additional_packaging()
    monkeypatch.setattr(module, "_GLOBAL_CONFIG_PATH", config)

    with pytest.raises(KeyError):
        module.make_command_distribution_toggleable(tmp_path)
