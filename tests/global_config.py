"""Shared access to geoip/globalConfig.json for the drift tests."""

import json
from pathlib import Path
from typing import Any

GLOBAL_CONFIG_PATH = Path(__file__).parent.parent / "geoip" / "globalConfig.json"


def load_global_config() -> dict[str, Any]:
    """Return the parsed globalConfig.json."""
    return json.loads(GLOBAL_CONFIG_PATH.read_text())  # type: ignore[no-any-return]


def load_custom_search_commands() -> list[dict[str, Any]]:
    """Return the customSearchCommand entries from globalConfig.json."""
    commands: list[dict[str, Any]] = load_global_config()["customSearchCommand"]
    return commands
