"""Custom REST handler for geoip settings that triggers database update on save.

Why this file exists:
    Normally, UCC generates this file from globalConfig.json with the default
    AdminExternalHandler. We need a custom handler to trigger background database
    updates when account credentials are saved.

    UCC's restHandlerModule/restHandlerClass mechanism only works for multi-instance
    tables (like the databases tab), not for single-instance forms like the account
    tab. So we must provide our own complete handler file.

Why field definitions are duplicated:
    globalConfig.json defines the fields for the UI (labels, help text, error
    messages). This file defines them for REST API validation (server-side).
    Both are needed. UCC either generates this entire file OR copies ours - it
    can't merge them. The field specs live in SETTINGS_FIELD_SPECS (geoip_utils.py)
    so that tests can compare them against globalConfig.json to catch drift.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import import_declare_test
from geoip_handler import trigger_background_update
from geoip_utils import SETTINGS_FIELD_SPECS
from splunktaucclib.rest_handler import admin_external
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
from splunktaucclib.rest_handler.endpoint import (
    MultipleModel,
    RestModel,
    field,
    validator,
)

if TYPE_CHECKING:
    from splunktaucclib.rest_handler.admin_external import ConfInfo

# NOTE: UCC-generated handlers include util.remove_http_proxy_env_vars() here,
# which strips HTTP_PROXY/HTTPS_PROXY from the environment. We intentionally
# omit this because our background thread downloads from MaxMind and should
# respect proxy settings if the user's environment requires them.


def _build_rest_fields(
    specs: list[dict[str, Any]],
) -> list[field.RestField]:
    """Build RestField objects from SETTINGS_FIELD_SPECS entries."""
    result = []
    for spec in specs:
        validators = [_build_validator(v) for v in spec.get("validators", [])]
        if len(validators) > 1:
            val = validator.AllOf(*validators)
        elif validators:
            val = validators[0]
        else:
            val = None
        result.append(
            field.RestField(
                spec["field"],
                required=spec["required"],
                encrypted=spec["encrypted"],
                default=spec.get("default"),
                validator=val,
            )
        )
    return result


def _build_validator(spec: dict[str, Any]) -> object:
    """Build a validator from a spec dict."""
    if spec["type"] == "regex":
        return validator.Pattern(regex=spec["pattern"])
    if spec["type"] == "string":
        return validator.String(min_len=spec["min_len"], max_len=spec["max_len"])
    msg = f"Unknown validator type: {spec['type']}"
    raise ValueError(msg)


fields_account = _build_rest_fields(SETTINGS_FIELD_SPECS["account"])
model_account = RestModel(fields_account, name="account")

fields_logging = _build_rest_fields(SETTINGS_FIELD_SPECS["logging"])
model_logging = RestModel(fields_logging, name="logging")


endpoint = MultipleModel(
    "geoip_settings",
    models=[
        model_account,
        model_logging,
    ],
    need_reload=False,
)


class GeoipSettingsHandler(AdminExternalHandler):
    """REST handler for geoip settings.

    Triggers a background database update after account credentials are saved.
    """

    def handleEdit(self, confInfo: ConfInfo) -> None:
        """Handle settings updates."""
        AdminExternalHandler.handleEdit(self, confInfo)
        # Only trigger update for account changes, not logging changes
        if self.callerArgs.id == "account":
            trigger_background_update(self.getSessionKey())

    def handleCreate(self, confInfo: ConfInfo) -> None:
        """Handle initial settings creation."""
        AdminExternalHandler.handleCreate(self, confInfo)
        if self.callerArgs.id == "account":
            trigger_background_update(self.getSessionKey())


# Entry point: Splunk runs this file as a script when handling REST API requests
# for the settings endpoint. admin_external.handle() parses the request, calls
# the appropriate handler method, and returns the response.
if __name__ == "__main__":
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=GeoipSettingsHandler,
    )
