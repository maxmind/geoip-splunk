"""Custom REST handlers that trigger database update after config saves.

This module is never run directly. It is imported by the UCC-generated wrapper
(geoip_rh_databases.py) and by geoip_rh_settings.py, both of which run
import_declare_test first to add lib/ to sys.path.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from geoip_utils import get_logger
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler

if TYPE_CHECKING:
    from splunktaucclib.rest_handler.admin_external import ConfInfo


class GeoipDatabasesHandler(AdminExternalHandler):
    """REST handler for database configuration.

    Triggers a background database update after databases are added/edited.
    Does not trigger on removal since there is nothing to download.
    """

    def handleEdit(self, confInfo: ConfInfo) -> None:
        """Handle database entry updates."""
        AdminExternalHandler.handleEdit(self, confInfo)
        trigger_background_update(self.getSessionKey())

    def handleCreate(self, confInfo: ConfInfo) -> None:
        """Handle new database entry creation."""
        AdminExternalHandler.handleCreate(self, confInfo)
        trigger_background_update(self.getSessionKey())


def trigger_background_update(session_key: str) -> None:
    """Spawn a background thread to update databases.

    Concurrent updates are safe because the vendored geoipupdate library
    acquires a file lock before writing databases.
    """
    get_logger(session_key).info("Triggering background database update")
    # daemon=False so the process stays alive until the download finishes.
    # Splunk's REST handler process exits after admin_external.handle()
    # returns; a daemon thread would be killed immediately. With a non-daemon
    # thread, the REST response is already written so the UI doesn't block,
    # but the process lingers until the download completes.
    thread = threading.Thread(
        target=_run_update_background,
        args=(session_key,),
        daemon=False,
    )
    thread.start()


def _run_update_background(session_key: str) -> None:
    """Run the database update in a background thread."""
    try:
        from geoipupdate_input import run_database_update

        run_database_update(session_key)
    except Exception:
        get_logger(session_key).exception("Background database update failed")
