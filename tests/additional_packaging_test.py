"""Tests for the UCC post-build hook in geoip/additional_packaging.py."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_MODULE_PATH = Path(__file__).parent.parent / "geoip" / "additional_packaging.py"

# What UCC's custom command template generates (abbreviated), containing
# all three markers the hook rewrites.
_GENERATED_WRAPPER = """\
import sys
import import_declare_test

from splunklib.searchcommands import \\
    dispatch, StreamingCommand, Configuration, Option, validators
from geoip_command import stream

@Configuration()
class GeoipCommand(StreamingCommand):

    databases = Option(name='databases', require=True)

    def stream(self, events):
        return stream(self, events)

dispatch(GeoipCommand, sys.argv, sys.stdin, sys.stdout, __name__)
"""


def _load_additional_packaging() -> ModuleType:
    spec = importlib.util.spec_from_file_location("additional_packaging", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_wrapper(tmp_path: Path, content: str) -> Path:
    wrapper = tmp_path / "bin" / "geoip.py"
    wrapper.parent.mkdir()
    wrapper.write_text(content)
    return wrapper


def test_make_command_distribution_toggleable_rewrites_wrapper(
    tmp_path: Path,
) -> None:
    wrapper = _write_wrapper(tmp_path, _GENERATED_WRAPPER)

    _load_additional_packaging().make_command_distribution_toggleable(tmp_path)

    result = wrapper.read_text()
    assert "from geoip_command import prepare, stream" in result
    assert "@Configuration(distributed=False)" in result
    assert (
        "    def prepare(self):\n        prepare(self)\n\n    def stream(self, events):"
    ) in result
    # The rewritten wrapper must still be valid Python.
    compile(result, str(wrapper), "exec")


@pytest.mark.parametrize(
    "marker",
    [
        "from geoip_command import stream",
        "@Configuration()",
        "    def stream(self, events):",
    ],
)
def test_make_command_distribution_toggleable_raises_without_marker(
    tmp_path: Path,
    marker: str,
) -> None:
    _write_wrapper(tmp_path, _GENERATED_WRAPPER.replace(marker, "# removed"))

    with pytest.raises(RuntimeError, match="template may have changed"):
        _load_additional_packaging().make_command_distribution_toggleable(tmp_path)
