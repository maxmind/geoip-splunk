"""Tests for the UCC post-build hook in geoip/additional_packaging.py."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_MODULE_PATH = Path(__file__).parent.parent / "geoip" / "additional_packaging.py"


def _load_additional_packaging() -> ModuleType:
    spec = importlib.util.spec_from_file_location("additional_packaging", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_command_search_head_only_rewrites_decorator(tmp_path: Path) -> None:
    wrapper = tmp_path / "bin" / "geoip.py"
    wrapper.parent.mkdir()
    wrapper.write_text(
        "@Configuration()\nclass GeoipCommand(StreamingCommand):\n    pass\n"
    )

    _load_additional_packaging().make_command_search_head_only(tmp_path)

    assert "@Configuration(distributed=False)" in wrapper.read_text()


def test_make_command_search_head_only_raises_without_marker(
    tmp_path: Path,
) -> None:
    wrapper = tmp_path / "bin" / "geoip.py"
    wrapper.parent.mkdir()
    wrapper.write_text("@Configuration(distributed=False)\n")

    with pytest.raises(RuntimeError):
        _load_additional_packaging().make_command_search_head_only(tmp_path)
