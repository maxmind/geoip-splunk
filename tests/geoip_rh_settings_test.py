"""Tests verifying SETTINGS_FIELD_SPECS stays in sync with globalConfig.json.

geoip_rh_settings.py builds its RestField definitions from SETTINGS_FIELD_SPECS
in geoip_utils.py. These tests verify those specs match globalConfig.json so the
two files don't drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from geoip_utils import SETTINGS_FIELD_SPECS

repo_root = Path(__file__).parent.parent
global_config_path = repo_root / "geoip" / "globalConfig.json"

# The logging tab is a UCC builtin ({"type": "loggingTab"}) with no entity
# list to compare against.
_LOGGING_TAB = "logging"


def _load_global_config() -> dict[str, Any]:
    with global_config_path.open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def _settings_tabs() -> list[str]:
    """Names of the settings tabs defined in globalConfig.json.

    Derived rather than hardcoded so a tab added there and forgotten in
    SETTINGS_FIELD_SPECS fails a test instead of being skipped. Multi-
    instance tables (the databases tab) are a separate endpoint with their
    own conf file, so they are not part of these specs.
    """
    tabs = _load_global_config()["pages"]["configuration"]["tabs"]
    return [t["name"] for t in tabs if "name" in t and "table" not in t]


_TABS = _settings_tabs()


def _get_config_tab(config: dict[str, Any], tab_name: str) -> dict[str, Any]:
    """Get a configuration tab by name from globalConfig.json."""
    tabs = config["pages"]["configuration"]["tabs"]
    return next(t for t in tabs if t.get("name") == tab_name)


@pytest.mark.parametrize("tab_name", _TABS)
def test_field_names_match(tab_name: str) -> None:
    config = _load_global_config()
    tab = _get_config_tab(config, tab_name)

    config_fields = [e["field"] for e in tab["entity"]]
    spec_fields = [f["field"] for f in SETTINGS_FIELD_SPECS[tab_name]]

    assert spec_fields == config_fields


@pytest.mark.parametrize("tab_name", _TABS)
def test_field_required_and_encrypted_match(tab_name: str) -> None:
    config = _load_global_config()
    tab = _get_config_tab(config, tab_name)

    for entity in tab["entity"]:
        field_name = entity["field"]
        spec = next(
            s for s in SETTINGS_FIELD_SPECS[tab_name] if s["field"] == field_name
        )

        assert spec["required"] == entity.get("required", False), (
            f"'required' mismatch for field '{field_name}'"
        )
        assert spec["encrypted"] == entity.get("encrypted", False), (
            f"'encrypted' mismatch for field '{field_name}'"
        )


@pytest.mark.parametrize("tab_name", _TABS)
def test_validator_patterns_match(tab_name: str) -> None:
    config = _load_global_config()
    tab = _get_config_tab(config, tab_name)

    for entity in tab["entity"]:
        field_name = entity["field"]
        spec = next(
            s for s in SETTINGS_FIELD_SPECS[tab_name] if s["field"] == field_name
        )

        config_validators: list[dict[str, Any]] = entity.get("validators", [])
        spec_validators: list[dict[str, Any]] = spec.get("validators", [])  # type: ignore[assignment]

        assert len(spec_validators) == len(config_validators), (
            f"Validator count mismatch for field '{field_name}'"
        )

        for config_v, spec_v in zip(config_validators, spec_validators, strict=True):
            assert spec_v["type"] == config_v["type"], (
                f"Validator type mismatch for field '{field_name}'"
            )
            if config_v["type"] == "regex":
                assert spec_v["pattern"] == config_v["pattern"], (
                    f"Regex pattern mismatch for field '{field_name}'"
                )
            elif config_v["type"] == "string":
                assert spec_v["min_len"] == config_v["minLength"], (
                    f"min_len mismatch for field '{field_name}'"
                )
                assert spec_v["max_len"] == config_v["maxLength"], (
                    f"max_len mismatch for field '{field_name}'"
                )


def test_logging_field_exists() -> None:
    spec_fields = [f["field"] for f in SETTINGS_FIELD_SPECS["logging"]]
    assert "loglevel" in spec_fields


def test_specs_cover_exactly_the_configured_tabs() -> None:
    """Every settings tab in globalConfig.json needs a spec, and vice
    versa: a spec-less tab cannot be saved through the REST endpoint, and a
    tab-less spec is a stanza nothing writes."""
    assert set(SETTINGS_FIELD_SPECS) == {*_TABS, _LOGGING_TAB}
