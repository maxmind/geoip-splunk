"""Tests verifying SETTINGS_FIELD_SPECS stays in sync with globalConfig.json.

geoip_rh_settings.py builds its RestField definitions from SETTINGS_FIELD_SPECS
in geoip_utils.py. These tests verify those specs match globalConfig.json so the
two files don't drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geoip_utils import SETTINGS_FIELD_SPECS

repo_root = Path(__file__).parent.parent
global_config_path = repo_root / "geoip" / "globalConfig.json"


def _load_global_config() -> dict[str, Any]:
    with global_config_path.open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def _get_config_tab(config: dict[str, Any], tab_name: str) -> dict[str, Any]:
    """Get a configuration tab by name from globalConfig.json."""
    tabs = config["pages"]["configuration"]["tabs"]
    return next(t for t in tabs if t.get("name") == tab_name)


def test_account_field_names_match() -> None:
    config = _load_global_config()
    account_tab = _get_config_tab(config, "account")

    config_fields = [e["field"] for e in account_tab["entity"]]
    spec_fields = [f["field"] for f in SETTINGS_FIELD_SPECS["account"]]

    assert spec_fields == config_fields


def test_account_field_required_and_encrypted_match() -> None:
    config = _load_global_config()
    account_tab = _get_config_tab(config, "account")

    for entity in account_tab["entity"]:
        field_name = entity["field"]
        spec = next(
            s for s in SETTINGS_FIELD_SPECS["account"] if s["field"] == field_name
        )

        assert spec["required"] == entity.get("required", False), (
            f"'required' mismatch for field '{field_name}'"
        )
        assert spec["encrypted"] == entity.get("encrypted", False), (
            f"'encrypted' mismatch for field '{field_name}'"
        )


def test_account_validator_patterns_match() -> None:
    config = _load_global_config()
    account_tab = _get_config_tab(config, "account")

    for entity in account_tab["entity"]:
        field_name = entity["field"]
        spec = next(
            s for s in SETTINGS_FIELD_SPECS["account"] if s["field"] == field_name
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
