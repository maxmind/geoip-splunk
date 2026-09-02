"""Tests for geoip/package/lib/requirements.txt.

The app's runtime dependencies are vendored into the package from this
file, while the test suite imports whatever uv.lock resolved into the
dev venv. The two are updated by different Dependabot jobs (the pip job
cannot bump a dependency that caps its Python version below the one it
assumes, see CLAUDE.md), so without this check a uv PR can bump a
package the tests run against while the shipped pin stays behind.
"""

import re
import tomllib
from pathlib import Path

repo_root = Path(__file__).parent.parent

_REQUIREMENTS = repo_root / "geoip" / "package" / "lib" / "requirements.txt"
_PYTHON_VERSION = _REQUIREMENTS.with_name(".python-version")
_UV_LOCK = repo_root / "uv.lock"

_EXACT_PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>\S+)$")


def _normalize(name: str) -> str:
    # PEP 503 name normalization, the form uv.lock uses.
    return re.sub(r"[-_.]+", "-", name).lower()


def _load_requirement_lines() -> list[str]:
    lines = (line.strip() for line in _REQUIREMENTS.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _load_requirement_pins() -> dict[str, str]:
    pins = {}
    for line in _load_requirement_lines():
        match = _EXACT_PIN.match(line)
        assert match is not None, f"not an exact pin: {line!r}"
        pins[_normalize(match["name"])] = match["version"]
    return pins


def _load_locked_versions() -> dict[str, str]:
    lock = tomllib.loads(_UV_LOCK.read_text())
    return {package["name"]: package["version"] for package in lock["package"]}


def test_every_requirement_is_an_exact_pin() -> None:
    # The build vendors exactly what is listed, so a range here would
    # make the shipped version depend on when the build ran.
    assert len(_load_requirement_pins()) == len(_load_requirement_lines())


def test_pins_match_the_versions_the_tests_run_against() -> None:
    pins = _load_requirement_pins()
    locked = _load_locked_versions()
    shared = sorted(pins.keys() & locked.keys())
    # The check is only meaningful for packages the dev venv installs.
    assert shared, "no runtime pin is present in uv.lock"
    mismatches = {
        name: (pins[name], locked[name])
        for name in shared
        if pins[name] != locked[name]
    }
    assert mismatches == {}, (
        f"requirements.txt pin differs from uv.lock (pinned, locked): {mismatches}"
    )


def test_python_version_file_names_a_full_3_13_release() -> None:
    # Dependabot's pip job reads this file to pick the Python it resolves
    # against, but only accepts a version that appears verbatim in
    # "pyenv install --list". pyenv has no bare "3.13" definition, so a
    # two-part version is silently ignored and the job falls back to the
    # newest Python it ships, which solnlib's "<3.14" cap rules out.
    version = _PYTHON_VERSION.read_text().strip()
    assert re.fullmatch(r"3\.13\.\d+", version), version
