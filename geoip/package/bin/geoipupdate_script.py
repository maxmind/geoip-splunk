"""Scripted input entry point for GeoIP database updates.

A thin alternative to the geoipupdate_input modular input. Splunk runs this on
the configured interval; with passAuth set on the [script://] stanza, Splunk
passes a session key on stdin, which we hand to the shared run_database_update()
function. The actual update logic lives in geoipupdate_input.py so it stays in
one place. This exists to test whether a scripted input runs on every search
head cluster member, unlike the modular input (GitHub #76).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from geoip_utils import get_fallback_logger, get_logger
from geoipupdate_input import run_database_update


def main() -> None:
    """Read the session key from stdin and run the database update."""
    raw = sys.stdin.read()
    session_key = raw.strip()
    if not session_key:
        # Log how many bytes arrived so we can tell "no token issued" (0 bytes)
        # apart from a token in an unexpected format.
        get_fallback_logger().error(
            "No session key on stdin (read %d bytes). Ensure passAuth is set on "
            "the script:// stanza and that Splunk has been fully restarted (not "
            "just reloaded) since it was added.",
            len(raw),
        )
        return

    # Make it obvious in the logs that this update was triggered by the
    # scripted input (geoipupdate_script.py), not the modular input, so we can
    # confirm which one ran on each search head cluster member (GitHub #76).
    get_logger(session_key).info(
        "Scripted input (geoipupdate_script.py) is running the database update",
    )

    run_database_update(session_key)


if __name__ == "__main__":
    main()
