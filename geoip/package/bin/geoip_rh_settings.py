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
from geoip_utils import (
    APP_NAME,
    DISTRIBUTION_STANZA,
    MMDB_ALLOW_NOTHING_PATTERN,
    MMDB_ALLOW_PATTERN,
    MMDB_ALLOWLIST_KEY,
    REPLICATION_ALLOWLIST_STANZA,
    RUN_ON_INDEXERS_FIELD,
    SETTINGS_FIELD_SPECS,
    get_fallback_logger,
    get_logger,
    is_truthy,
    sync_replication_marker,
)
from solnlib import conf_manager
from splunktaucclib.rest_handler import admin_external
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
from splunktaucclib.rest_handler.endpoint import (
    MultipleModel,
    RestModel,
    field,
    validator,
)
from splunktaucclib.rest_handler.error import RestError

if TYPE_CHECKING:
    from collections.abc import Callable

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

fields_distribution = _build_rest_fields(SETTINGS_FIELD_SPECS[DISTRIBUTION_STANZA])
model_distribution = RestModel(fields_distribution, name=DISTRIBUTION_STANZA)

fields_logging = _build_rest_fields(SETTINGS_FIELD_SPECS["logging"])
model_logging = RestModel(fields_logging, name="logging")


endpoint = MultipleModel(
    "geoip_settings",
    models=[
        model_account,
        model_distribution,
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
        if self.callerArgs.id == DISTRIBUTION_STANZA:
            self._save_distribution(confInfo, AdminExternalHandler.handleEdit)
            return
        AdminExternalHandler.handleEdit(self, confInfo)
        # Only trigger update for account changes, not logging changes
        if self.callerArgs.id == "account":
            trigger_background_update(self.getSessionKey())

    def handleCreate(self, confInfo: ConfInfo) -> None:
        """Handle initial settings creation.

        UCC generates handleractions = edit, list for this endpoint, so
        Splunk never dispatches create here in practice (all three stanzas
        ship in default/geoip_settings.conf). Kept as a safety net in case
        that changes; handleEdit is the path that actually runs.
        """
        if self.callerArgs.id == DISTRIBUTION_STANZA:
            self._save_distribution(confInfo, AdminExternalHandler.handleCreate)
            return
        AdminExternalHandler.handleCreate(self, confInfo)
        if self.callerArgs.id == "account":
            trigger_background_update(self.getSessionKey())

    def _save_distribution(
        self,
        confInfo: ConfInfo,
        save: Callable[[AdminExternalHandler, ConfInfo], None],
    ) -> None:
        """Save the distribution stanza and the distsearch override.

        The two writes are ordered so that a failure between them cannot
        leave the setting enabled while the allowlist still matches
        nothing - in that state every geoip search distributes, fails on
        the indexers, and a restart does not recover. Enabling writes
        distsearch first, so a failure leaves the toggle off; disabling
        saves the setting first, so a failure leaves only extra
        replication, which does not break searches.

        The bundle state marker comes last, once both writes committed the
        new state, so a failed save cannot record a state that was rolled
        back. Written here as well as by the updater input because this
        member's marker gets its fresh mtime immediately - before the
        restart the toggle requires - and that mtime is what guarantees
        the post-restart bundle a checksum no search peer has seen (see
        sync_replication_marker).

        The logger is resolved up front, with the fallback, because
        get_logger reads the log level over REST and can itself raise:
        a raise from a later logging call would escape as an opaque 500 -
        after save() has committed, on the disable path - instead of this
        module's RestError with the real failure.
        """
        try:
            logger = get_logger(self.getSessionKey())
        except Exception:
            logger = get_fallback_logger()
            logger.exception("Could not build the configured logger")
        run_on_indexers = _parse_run_on_indexers(self.callerArgs.data)
        if run_on_indexers:
            _apply_mmdb_replication(self.getSessionKey(), logger, run_on_indexers=True)
            save(self, confInfo)
        else:
            save(self, confInfo)
            _apply_mmdb_replication(self.getSessionKey(), logger, run_on_indexers=False)
        sync_replication_marker(logger, run_on_indexers=run_on_indexers)


def _parse_run_on_indexers(data: dict[str, Any]) -> bool:
    """Parse the run_on_indexers checkbox value from callerArgs data.

    callerArgs.data maps field names to lists of values; the checkbox
    posts "1" or "0".
    """
    values = data.get(RUN_ON_INDEXERS_FIELD) or [None]
    return is_truthy(values[0])


def _apply_mmdb_replication(
    session_key: str,
    logger: logging.Logger,
    *,
    run_on_indexers: bool,
) -> None:
    """Point the distsearch.conf allowlist override at the toggle's state.

    The databases live in the app's databases/ directory, which is not in
    Splunk's default knowledge bundle allowlist, so they only replicate to
    indexers through the geoip_mmdb [replicationAllowlist] key. The shipped
    default is a placeholder pattern that matches no real file (not an empty
    value, which in an allowlist matches everything); enabling "Run on
    indexers" overrides the key in local/distsearch.conf with the real
    pattern. Conf keys cannot be deleted through the REST API, so the key
    is always written with one of the two values.

    The logger comes from the caller so logging a failure cannot raise
    itself and mask the RestError (see _save_distribution).
    """
    pattern = MMDB_ALLOW_PATTERN if run_on_indexers else MMDB_ALLOW_NOTHING_PATTERN
    try:
        conf = conf_manager.ConfManager(session_key, APP_NAME).get_conf("distsearch")
        # ConfFile.update reads the stanza first and only creates it on an
        # HTTP 404, so the [replicationAllowlist] stanza the app ships in
        # default/distsearch.conf is what makes this resolve at all.
        conf.update(REPLICATION_ALLOWLIST_STANZA, {MMDB_ALLOWLIST_KEY: pattern})
    except Exception as e:
        logger.exception("Failed to update the distsearch.conf replication allowlist")
        if run_on_indexers:
            msg = (
                "Updating distsearch.conf failed, so the setting was not "
                f"saved and geoip searches will keep running on the search "
                f"head only. Save again to retry. Error: {e}"
            )
        else:
            msg = (
                "The setting was saved, but updating distsearch.conf failed, "
                f"so databases may keep replicating to the indexers. Save "
                f"again to retry. Error: {e}"
            )
        raise RestError(500, msg) from e
    logger.info(
        "Set distsearch.conf [replicationAllowlist] %s = %s (run_on_indexers=%s)",
        MMDB_ALLOWLIST_KEY,
        pattern,
        run_on_indexers,
    )


# Entry point: Splunk runs this file as a script when handling REST API requests
# for the settings endpoint. admin_external.handle() parses the request, calls
# the appropriate handler method, and returns the response.
if __name__ == "__main__":
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=GeoipSettingsHandler,
    )
