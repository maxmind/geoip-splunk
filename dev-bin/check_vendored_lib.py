"""Check that the built app's lib/ matches the exported requirements file.

The package must hold exactly the exported closure: one dist-info per pin
that applies to this platform, at the pinned version, and no other
package. pip's hash-checking mode is meant to guarantee this; build.sh
runs this check so a UCC or pip change cannot ship something else
silently.
"""

import re
import sys
from pathlib import Path

from packaging.markers import Marker
from packaging.utils import NormalizedName, canonicalize_name

repo_root = Path(__file__).parent.parent

_REQUIREMENTS = repo_root / "geoip" / "package" / "lib" / "requirements.txt"
_LIB = repo_root / "output" / "geoip" / "lib"

# "name==version", an optional marker, and the backslash that continues the
# line into its --hash options. The header comments and the indented --hash
# lines do not match.
_PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>\S+)"
    r"(?: ; (?P<marker>.*?))? *\\?$"
)

Pin = tuple[NormalizedName, str]


def main() -> None:
    """Exit non-zero if lib/ and the requirements file disagree."""
    pinned = _pinned()
    installed = _installed()
    if pinned != installed:
        sys.exit(
            f"{_LIB} does not match {_REQUIREMENTS}\n"
            f"  pinned but not installed: {sorted(pinned - installed)}\n"
            f"  installed but not pinned: {sorted(installed - pinned)}"
        )


def _pinned() -> set[Pin]:
    pins = set()
    for line in _REQUIREMENTS.read_text().splitlines():
        match = _PIN.match(line)
        if match is None:
            continue
        marker = match["marker"]
        if marker is None or Marker(marker).evaluate():
            pins.add((canonicalize_name(match["name"]), match["version"]))
    return pins


def _installed() -> set[Pin]:
    installed = set()
    for path in _LIB.glob("*.dist-info"):
        name, version = path.name.removesuffix(".dist-info").rsplit("-", 1)
        installed.add((canonicalize_name(name), version))
    return installed


if __name__ == "__main__":
    main()
