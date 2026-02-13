"""Modular input for downloading and updating MaxMind GeoIP databases."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from pygeoipupdate.models import UpdateResult

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from geoip_utils import (
    APP_NAME,
    get_database_directory,
    get_fallback_logger,
    get_logger,
)
from pygeoipupdate import Config, Updater
from pygeoipupdate.errors import GeoIPUpdateError
from solnlib import conf_manager
from solnlib.soln_exceptions import ConfManagerException, ConfStanzaNotExistException


class GeoIPUpdateInput:
    """Modular input for GeoIP database updates.

    This class implements the Splunk modular input interface without inheriting
    from Script, allowing it to be used in both the Splunk environment and tests.
    """

    def get_scheme(self) -> dict[str, object]:
        """Return the scheme for this modular input.

        Returns:
            Dictionary describing the input scheme.

        """
        return {
            "title": "GeoIP Database Update",
            "description": "Downloads and updates MaxMind GeoIP databases",
            "use_external_validation": False,
            "streaming_mode_xml": True,
            "use_single_instance": False,
            "args": [],
        }

    def validate_input(self, definition: object) -> None:
        """Validate the input configuration."""
        # No validation needed - credentials are validated when used

    def stream_events(self, inputs: object, _ew: object) -> None:
        """Run the database update.

        Args:
            inputs: The input definition from Splunk.
            _ew: The event writer from Splunk (unused, we use logging).

        """
        # Get session key from inputs
        # inputs has a metadata attribute from Splunk's InputDefinition
        session_key = inputs.metadata.get("session_key", "")  # type: ignore[attr-defined]
        if not session_key:
            get_fallback_logger().error("No session key provided by Splunk")
            return

        run_database_update(session_key)


def run_database_update(session_key: str) -> None:
    """Run the database update process.

    This is the main entry point for triggering database updates. It handles
    getting credentials, database names, and running the async update with
    proper error handling and logging.

    Args:
        session_key: Splunk session key for REST API calls.

    """
    logger = get_logger(session_key)

    try:
        account_id, license_key = _get_account_credentials(session_key)
        edition_ids = _get_database_names(session_key)
        database_directory = get_database_directory()

        database_directory.mkdir(parents=True, exist_ok=True)

        _run_update(
            account_id=account_id,
            license_key=license_key,
            edition_ids=edition_ids,
            database_directory=database_directory,
            logger=logger,
        )

        logger.info("Database update completed successfully")

    except ValueError as e:
        logger.warning("Skipping database update: %s", e)
    except GeoIPUpdateError:
        logger.exception("Database update failed")
    except Exception:
        logger.exception("Unexpected error during database update")


def _get_account_credentials(session_key: str) -> tuple[int, str]:
    """Get MaxMind account credentials from the configuration.

    Args:
        session_key: Splunk session key for REST API calls.

    Returns:
        Tuple of (account_id, license_key).

    Raises:
        ValueError: If credentials are not configured.

    """
    msg = (
        "MaxMind account credentials not configured. "
        "Go to Configuration > MaxMind Account to enter your credentials."
    )

    try:
        cfm = conf_manager.ConfManager(
            session_key,
            APP_NAME,
            realm=f"__REST_CREDENTIAL__#{APP_NAME}#configs/conf-{APP_NAME}_settings",
        )
        conf = cfm.get_conf(f"{APP_NAME}_settings")
        account_stanza = conf.get("account", only_current_app=True)
    except (ConfManagerException, ConfStanzaNotExistException) as e:
        raise ValueError(msg) from e

    account_id_str = account_stanza.get("account_id")
    license_key = account_stanza.get("license_key")

    if not account_id_str or not license_key:
        raise ValueError(msg)

    if not account_id_str.isdigit():
        msg = (
            f"MaxMind account ID must be a number, got '{account_id_str}'. "
            "Go to Configuration > MaxMind Account to correct your account ID."
        )
        raise ValueError(msg)

    return int(account_id_str), license_key


def _get_database_names(session_key: str) -> list[str]:
    """Get configured database names from the configuration.

    Args:
        session_key: Splunk session key for REST API calls.

    Returns:
        List of database names (edition IDs) to download.

    Raises:
        ValueError: If no databases are configured.

    """
    msg = (
        "No databases configured. "
        "Go to Configuration > Databases to add databases to download."
    )

    try:
        cfm = conf_manager.ConfManager(
            session_key,
            APP_NAME,
        )
        conf = cfm.get_conf(f"{APP_NAME}_databases")
    except ConfManagerException as e:
        raise ValueError(msg) from e

    # Get all stanzas except 'default'
    databases = [
        name for name in conf.get_all(only_current_app=True) if name != "default"
    ]

    if not databases:
        raise ValueError(msg)

    return databases


def _run_update(
    account_id: int,
    license_key: str,
    edition_ids: list[str],
    database_directory: Path,
    logger: logging.Logger,
) -> None:
    """Run the database update process.

    Args:
        account_id: MaxMind account ID.
        license_key: MaxMind license key.
        edition_ids: List of database edition IDs to download.
        database_directory: Directory to store databases.
        logger: Logger for output.

    """
    config = Config(
        account_id=account_id,
        license_key=license_key,
        edition_ids=tuple(edition_ids),
        database_directory=database_directory,
    )

    logger.info(
        "Starting database update for editions: %s",
        ", ".join(edition_ids),
    )

    async def _download() -> list[UpdateResult]:
        async with Updater(config) as updater:
            return await updater.run()

    results: list[UpdateResult] = asyncio.run(_download())

    for result in results:
        if result.was_updated:
            logger.info(
                "Updated %s: %s -> %s",
                result.edition_id,
                result.old_hash,
                result.new_hash,
            )
        else:
            logger.info(
                "%s is up to date (hash: %s)",
                result.edition_id,
                result.new_hash,
            )


# Entry point for Splunk modular input
if __name__ == "__main__":
    # Import here to avoid issues when module is imported for testing
    from splunklib.modularinput import Scheme, Script  # type: ignore[import-not-found]

    class GeoIPUpdateScript(GeoIPUpdateInput, Script):  # type: ignore[misc]
        """Splunk modular input script.

        Inherits from GeoIPUpdateInput first so its stream_events and
        validate_input implementations take precedence over Script's
        (which raise NotImplementedError).

        get_scheme is overridden here because Script.run() expects a
        Scheme object, not the plain dict that GeoIPUpdateInput returns.
        """

        def get_scheme(self) -> Scheme:
            """Return the Scheme object expected by Script.run()."""
            scheme = Scheme("GeoIP Database Update")
            scheme.description = "Downloads and updates MaxMind GeoIP databases"
            scheme.use_external_validation = False
            scheme.streaming_mode = Scheme.streaming_mode_xml
            scheme.use_single_instance = False
            return scheme

    sys.exit(GeoIPUpdateScript().run(sys.argv))
