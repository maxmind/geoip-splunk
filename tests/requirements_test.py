"""Tests for the runtime requirements export.

geoip/package/lib/requirements.txt is not tracked. build.sh generates it
from the runtime dependency group in uv.lock with
dev-bin/export-requirements.sh, so the package ships the versions the
test suite ran against. These tests run the same script and check its
output.
"""

import re
import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import NormalizedName, canonicalize_name

repo_root = Path(__file__).parent.parent

_EXPORT_SCRIPT = repo_root / "dev-bin" / "export-requirements.sh"
_PYPROJECT = repo_root / "pyproject.toml"
_UV_LOCK = repo_root / "uv.lock"

_HASH_OPTION = re.compile(r"\s+--hash=sha256:[0-9a-f]{64}")


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> list[Requirement]:
    output = tmp_path_factory.mktemp("export") / "requirements.txt"
    subprocess.run([_EXPORT_SCRIPT, output], check=True)  # noqa: S603
    # uv writes each requirement's hashes on backslash-continued lines.
    joined = output.read_text().replace("\\\n", " ")
    lines = [line.strip() for line in joined.splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    # pip only enforces the lock's hashes if every requirement carries one.
    without_hash = [line for line in lines if not _HASH_OPTION.search(line)]
    assert without_hash == []
    # The hash options are pip requirements-file syntax, not PEP 508.
    return [Requirement(_HASH_OPTION.sub("", line)) for line in lines]


def test_every_requirement_is_an_exact_pin(exported: list[Requirement]) -> None:
    # pip installs the file in hash-checking mode, which needs exact pins.
    not_pinned = [str(r) for r in exported if not _is_exact_pin(r)]
    assert not_pinned == []


def test_export_is_exactly_the_runtime_closure(exported: list[Requirement]) -> None:
    # Walk uv.lock from the runtime group's entries, independently of
    # "uv export", so both a lost --only-group (a dev tool in the package)
    # and a lost dependency (a package missing from it) fail here.
    exported_names = {canonicalize_name(r.name) for r in exported}
    assert exported_names == _runtime_closure()


def _is_exact_pin(requirement: Requirement) -> bool:
    specifiers = list(requirement.specifier)
    return len(specifiers) == 1 and specifiers[0].operator == "=="


def _runtime_closure() -> set[NormalizedName]:
    pyproject = tomllib.loads(_PYPROJECT.read_text())
    lock = tomllib.loads(_UV_LOCK.read_text())
    packages = {canonicalize_name(p["name"]): p for p in lock["package"]}

    # Pairs of (package, extra), where an extra of None means the package
    # itself. A PEP 735 {include-group = "..."} table names no package.
    pending: list[tuple[NormalizedName, str | None]] = []
    for entry in pyproject["dependency-groups"]["runtime"]:
        if not isinstance(entry, str):
            continue
        requirement = Requirement(entry)
        name = canonicalize_name(requirement.name)
        pending.append((name, None))
        pending.extend((name, extra) for extra in requirement.extras)

    closure: set[NormalizedName] = set()
    seen: set[tuple[NormalizedName, str | None]] = set()
    while pending:
        name, extra = pending.pop()
        if (name, extra) in seen:
            continue
        seen.add((name, extra))
        closure.add(name)
        package = packages[name]
        if extra is None:
            dependencies = package.get("dependencies", [])
        else:
            dependencies = package["optional-dependencies"][extra]
        for dependency in dependencies:
            dependency_name = canonicalize_name(dependency["name"])
            pending.append((dependency_name, None))
            pending.extend(
                (dependency_name, dependency_extra)
                for dependency_extra in dependency.get("extra", [])
            )
    return closure
