"""Shared utilities for the GeoIP app."""

import logging
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from solnlib import conf_manager
    from solnlib import log as solnlib_log
    from solnlib.soln_exceptions import ConfManagerException

    _HAS_SOLNLIB = True
except ImportError:
    _HAS_SOLNLIB = False


APP_NAME = "geoip"
CONF_NAME = f"{APP_NAME}_settings"

# The realm UCC's REST handlers store the encrypted account fields under in
# passwords.conf. solnlib needs it to decrypt the account stanza - reading
# the stanza without it raises CredentialNotExistException (verified on a
# live cluster) instead of returning the masked values.
SETTINGS_CREDENTIAL_REALM = f"__REST_CREDENTIAL__#{APP_NAME}#configs/conf-{CONF_NAME}"

# Whether the MaxMind databases ride the knowledge bundle to indexers is
# controlled through this [replicationAllowlist] key in distsearch.conf. The
# shipped default (default/distsearch.conf) is a pattern that matches no
# real file, keeping the databases out of the bundle; enabling "Run on
# indexers" overrides the key in local/distsearch.conf with the real
# pattern, since conf keys cannot be deleted through the REST API (see
# geoip_rh_settings.py).
MMDB_ALLOWLIST_KEY = "geoip_mmdb"

# The distsearch.conf stanza both the shipped default and the override live
# in. Shared so the handler, the shipped conf, and their tests cannot drift:
# a rename that reaches only some of them would put the override in a stanza
# splunkd ignores, leaving the placeholder effective while the setting reads
# as enabled - the state every geoip search fails in.
REPLICATION_ALLOWLIST_STANZA = "replicationAllowlist"

# Allow pattern: databases ride the bundle (indexer execution on).
MMDB_ALLOW_PATTERN = "apps/geoip/databases/*.mmdb"

# Allow-nothing pattern: matches no real file, so the databases stay out of
# the bundle (indexer execution off).
MMDB_ALLOW_NOTHING_PATTERN = "apps/geoip/databases/allow-nothing-placeholder"

# The knowledge bundle state marker (see sync_replication_marker). Lives in
# the app's lookups/ directory because that is in Splunk's default bundle
# replication allowlist, so the marker is in the bundle under both toggle
# states - which is what lets a marker change alter the bundle checksum.
# lookups/ is also swept into search head cluster replication summaries -
# the reason the databases live in databases/ instead (see
# get_database_directory) - but that is harmless for a few-byte marker:
# direct disk writes are not journaled, so each member maintains its own
# copy in steady state, and a destructive resync rewriting it from the
# captain's baseline converges to the same state, since every member
# derives the content from the same replicated setting.
REPLICATION_MARKER_FILENAME = "geoip_replication_state.csv"

# Conf coordinates of the "Run on indexers" toggle in geoip_settings.conf:
# the stanza (also the settings tab's REST id) and the field within it.
# Shared by the settings handler, which writes the stanza, and the search
# command, which reads it per search, so the two sides cannot drift.
DISTRIBUTION_STANZA = "distribution"
RUN_ON_INDEXERS_FIELD = "run_on_indexers"

# Field specifications for the settings REST handler (geoip_rh_settings.py).
# That file builds RestField objects from these specs. Tests compare these
# specs against globalConfig.json to catch drift between the two files.
SETTINGS_FIELD_SPECS = {
    "account": [
        {
            "field": "account_id",
            "required": True,
            "encrypted": True,
            "default": None,
            "validators": [
                {"type": "regex", "pattern": r"^[0-9]+$"},
                {"type": "string", "min_len": 1, "max_len": 20},
            ],
        },
        {
            "field": "license_key",
            "required": True,
            "encrypted": True,
            "default": None,
            "validators": [
                {"type": "regex", "pattern": r"^[A-Za-z0-9_]+$"},
                {"type": "string", "min_len": 8, "max_len": 100},
            ],
        },
    ],
    DISTRIBUTION_STANZA: [
        {
            # Checkbox: stored as 1/0. UCC checkbox entities do not take
            # validators.
            "field": RUN_ON_INDEXERS_FIELD,
            "required": False,
            "encrypted": False,
            "default": 0,
            "validators": [],
        },
    ],
    "logging": [
        {
            "field": "loglevel",
            "required": True,
            "encrypted": False,
            "default": "INFO",
            "validators": [
                {
                    "type": "regex",
                    "pattern": r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
                },
            ],
        },
    ],
}


def is_truthy(value: object) -> bool:
    """Whether a conf or REST value represents true.

    Splunk checkboxes and conf files store booleans as "1"/"0"; accept a
    few common spellings. Shared by the settings handler and the search
    command so both sides of the "Run on indexers" toggle agree.
    """
    return str(value).strip().lower() in ("1", "true", "yes")


# Valid database name pattern (alphanumeric, underscores, and hyphens only)
_VALID_DB_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_database_name(name: str) -> bool:
    """Whether a database name is safe to join onto the database directory.

    Database names arrive from search arguments and user configuration
    and become file paths, so restrict them to characters that cannot
    traverse paths. Shared by the geoip and geoipdebug commands.
    """
    return bool(_VALID_DB_NAME.match(name))


def fill_missing_event_fields(events: list[dict[str, Any]]) -> None:
    """Give every event the union of all events' fields, in place.

    The SDK's record writer locks the output field set to the keys of the
    first record it writes in each output chunk (splunklib
    internals.RecordWriter._write_record; RecordWriterV2._clear resets it
    per chunk), so a field that only later events in the chunk have would
    silently vanish from the results. Backfilling with None keeps the
    value empty in the output, like a genuinely absent field.

    Shared by the geoip and geoipdebug commands, whose events' fields
    vary per event: the database fields depend on the IP looked up, and
    the diagnostic fields depend on the component.
    """
    all_fields = {key: None for event in events for key in event}
    for event in events:
        for key in all_fields:
            event.setdefault(key, None)


def migrate_legacy_databases(logger: logging.Logger) -> None:
    """Move databases from the pre-1.2.0 location into databases/.

    Releases before 1.2.0 stored the databases in the app's local/data/
    directory (resolved via $SPLUNK_HOME). Files left there after an
    upgrade would sit in search head cluster replication summaries
    indefinitely, and the geoip command would error until the updater
    re-downloaded everything. Called by the updater at the start of each
    run and by the geoip command when a database is missing; once the
    old directory is gone this is a single stat() no-op.

    The move never overwrites: os.link raises FileExistsError when the
    destination exists, which means the updater already downloaded a
    fresher copy there, so the legacy file is only deleted. Both
    directories are under the app root, on one filesystem. Never raises:
    a failed migration must not take down a search or an update run -
    the files are re-downloadable.
    """
    splunk_home = os.environ.get("SPLUNK_HOME", "/opt/splunk")
    legacy_dir = Path(splunk_home, "etc", "apps", APP_NAME, "local", "data")
    if not legacy_dir.is_dir():
        return
    try:
        database_directory = get_database_directory()
        database_directory.mkdir(parents=True, exist_ok=True)
        for legacy_path in sorted(legacy_dir.glob("*.mmdb")):
            new_path = database_directory / legacy_path.name
            try:
                os.link(legacy_path, new_path)
            except FileExistsError:
                logger.info(
                    "Removing legacy database %s: %s already exists",
                    legacy_path,
                    new_path,
                )
            except FileNotFoundError:
                _log_migration_enoent(logger, legacy_path, new_path)
                continue
            except OSError:
                # One unmigratable file (left root-owned by a manual copy,
                # an immutable or SELinux bit, EMLINK, ENOSPC) is that
                # file's problem alone. Reaching the handler below would
                # abandon every remaining database, and since sorted() fixes
                # the order the same file would block them on every later
                # run as well.
                logger.exception("Failed to migrate legacy database %s", legacy_path)
                continue
            else:
                logger.info("Migrated database %s to %s", legacy_path, new_path)
            legacy_path.unlink(missing_ok=True)
        # The old updater's scratch files, removed so rmdir can succeed.
        for leftover in (
            *legacy_dir.glob("*.temporary"),
            legacy_dir / ".geoipupdate.lock",
        ):
            leftover.unlink(missing_ok=True)
        try:
            legacy_dir.rmdir()
        except OSError:
            # Anything the globs above do not cover (a .mmdb.gz, a stale
            # .md5, a subdirectory, a database this run could not move)
            # keeps the directory alive, and with it the search head
            # cluster replication summary entries the migration exists to
            # remove. Say so rather than treating it as success.
            logger.warning(
                "Left %s in place; unexpected files remain there and will "
                "stay in search head cluster replication summaries: %s",
                legacy_dir,
                ", ".join(sorted(p.name for p in legacy_dir.iterdir())),
            )
    except Exception:  # migration must never take down the caller
        logger.exception("Failed to migrate databases from %s", legacy_dir)


def _log_migration_enoent(
    logger: logging.Logger,
    legacy_path: Path,
    new_path: Path,
) -> None:
    """Log an ENOENT raised by the os.link in migrate_legacy_databases.

    os.link raises ENOENT for either operand. A vanished source is the
    benign case - a concurrent migration moved it first - but anything else
    (a destination directory removed since the mkdir) would otherwise skip
    every database without a word.
    """
    if legacy_path.exists():
        logger.warning(
            "Could not migrate legacy database %s to %s: no such file or "
            "directory (the destination directory may be gone)",
            legacy_path,
            new_path,
        )
        return
    logger.debug(
        "Legacy database %s vanished; a concurrent migration moved it first",
        legacy_path,
    )


def get_database_directory() -> Path:
    """Get the directory where MaxMind databases are stored.

    Database storage location: the app's databases/ directory, located
    relative to this file (<app root>/lib/geoip_utils.py -> <app
    root>/databases/).

    Why databases/ (a custom app-level directory):
    - It is outside search head cluster conf replication summaries, which
      capture only local/..., lookups/*, and metadata: members do not
      re-summarize hundreds of MB of binaries every minute, a destructive
      resync cannot rewrite a database in place mid-read, and no
      conf_replication_summary excludelist in server.conf (which
      AppInspect rejects) is needed to prevent any of that
    - It is outside Splunk's default knowledge bundle allowlist (app bin/
      and lookups/), so whether the databases replicate to indexers is
      controlled solely by the app's own distsearch.conf allowlist entry
    - Resolving the path relative to this file works both when the app is
      installed ($SPLUNK_HOME/etc/apps/geoip/) and when it runs from a
      knowledge bundle on an indexer
      ($SPLUNK_HOME/var/run/searchpeers/<bundle>/apps/geoip/)

    Why NOT other locations:
    - lookups/: rides the knowledge bundle for free via the default
      allowlist, but is swept into SHC replication summaries, and keeping
      the databases out of those requires the server.conf excludelist
      AppInspect rejects
    - local/data/ (the previous location): local/... is recursively
      included in SHC replication summaries too, and $SPLUNK_HOME-based
      resolution breaks on indexers where the app root is not under
      etc/apps
    - /default/ or package /data/: Overwritten on upgrades, read-only after
      install
    - $SPLUNK_HOME/var/lib/splunk/: Not a standard app data location
    - $SPLUNK_HOME/share/: System directory, not for app data
    - KV Store: Only for structured data, not binary files like .mmdb

    References:
    - https://docs.splunk.com/Documentation/Splunk/latest/Admin/Apparchitectureandobjectownership
    - https://docs.splunk.com/Documentation/Splunk/latest/Admin/Configurationfiledirectories
    - https://docs.splunk.com/Documentation/Splunk/latest/DistSearch/Whatsearchheadssend

    Returns:
        Path to the database directory.

    """
    # Allow override via environment variable (for testing)
    if env_dir := os.environ.get("MAXMIND_DB_DIR"):
        return Path(env_dir)

    return Path(__file__).resolve().parent.parent / "databases"


def sync_replication_marker(
    logger: logging.Logger,
    *,
    run_on_indexers: bool,
) -> None:
    """Record the "Run on indexers" state in the bundle state marker.

    Splunk identifies a knowledge bundle by a checksum over the bundle's
    file metadata, and when a freshly built bundle's checksum matches a
    bundle a search peer already holds, it skips the upload without
    switching the peer to it (verified on a live cluster).
    Toggling "Run on indexers" flips the bundle between two recurring
    states, so on an otherwise quiet cluster the rebuilt bundle after a
    toggle-plus-restart matches a stale bundle in the peer's inventory
    and the toggle silently never takes effect on the peers - enabled but
    absent databases fail every distributed geoip search, indefinitely.

    Rewriting an always-replicated file on every state change breaks the
    recurrence: the rewrite's fresh mtime gives the next bundle a checksum
    no peer has seen. The mtime is the entire mechanism - the checksum
    covers file metadata, and both states of this file are the same size -
    so a rewrite that preserved the mtime would silently reinstate the
    bug; the recorded value exists to make the sync idempotent and the
    state inspectable. The settings handler writes the marker on save (a
    pre-restart write is enough - its fresh mtime rides into the
    post-restart bundle) and the updater input syncs it each run,
    covering members that did not serve the save; the bundle follows the
    captain's files, and any member can be captain.

    No-op when the marker already records the state, so steady state
    never rebuilds the bundle. Never raises: the marker is a reliability
    aid, and failing to write it must not take down a settings save or an
    update run.
    """
    content = f"{RUN_ON_INDEXERS_FIELD}\n{1 if run_on_indexers else 0}\n"
    # Resolved outside the try so the failure log below can name the path;
    # pure computation (an environment read and string joins), so it does
    # not endanger the never-raises promise.
    marker_path = get_replication_marker_path()
    try:
        try:
            if marker_path.read_text(encoding="ascii") == content:
                return
        except (OSError, UnicodeDecodeError):
            pass  # missing or unreadable: (re)write it
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        # Write-and-rename so a bundle build cannot pick up a torn write.
        # mkstemp gives each concurrent writer (a settings save in one
        # process overlapping an updater run in another, say) its own
        # exclusively created scratch file, the same way pygeoipupdate
        # writes the databases, and Splunk's default replication denylist
        # excludes lookups/*.tmp, so the scratch file never rides the
        # bundle itself.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{marker_path.name}.",
            suffix=".tmp",
            dir=marker_path.parent,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as tmp_file:
                if hasattr(os, "fchmod"):
                    # mkstemp creates the file 0600; give the marker the
                    # mode a plain create would have.
                    os.fchmod(tmp_file.fileno(), 0o644)
                tmp_file.write(content)
            tmp_path.replace(marker_path)
        finally:
            # replace() consumed the scratch file on success, so this
            # only removes it after a failure.
            tmp_path.unlink(missing_ok=True)
    except Exception:  # the marker must never take down the caller
        logger.exception(
            "Failed to write the bundle state marker %s; a changed "
            '"Run on indexers" setting may not reach the search peers '
            "until some other replicated app file changes",
            marker_path,
        )
    else:
        logger.info(
            "Recorded run_on_indexers=%s in %s",
            run_on_indexers,
            marker_path,
        )


def get_replication_marker_path() -> Path:
    """Get the path of the knowledge bundle state marker.

    Resolved relative to this file like get_database_directory; the
    GEOIP_LOOKUPS_DIR environment variable overrides the directory for
    tests.
    """
    if env_dir := os.environ.get("GEOIP_LOOKUPS_DIR"):
        return Path(env_dir) / REPLICATION_MARKER_FILENAME
    return (
        Path(__file__).resolve().parent.parent / "lookups" / REPLICATION_MARKER_FILENAME
    )


def get_run_on_indexers_setting(session_key: str) -> object | None:
    """Read the raw "Run on indexers" value from geoip_settings.conf.

    Reads through solnlib with app_name pinned to the geoip app, like
    get_logger: the geoip command can be dispatched from any app, and the
    SDK's command.service is namespaced to the dispatching app, so a read
    through it resolves the conf only via the app's export = system
    metadata. Pinning the namespace removes that dependency.

    Raises on any failure, including solnlib being unavailable (it is not
    part of the knowledge bundle, but the setting is only read on the
    search head); callers decide the fallback.
    """
    return get_setting(session_key, DISTRIBUTION_STANZA, RUN_ON_INDEXERS_FIELD)


def get_setting(session_key: str, stanza_name: str, field: str) -> object | None:
    """Read one field of geoip_settings.conf.

    The shipped default/geoip_settings.conf (UCC generates it from the
    globalConfig defaults) means the conf and its stanzas exist on any
    healthy install, and the conf endpoint merges default/ and local/.
    So there is no missing-because-never-saved case to soften: a read
    that fails is abnormal and raises, including when solnlib is
    unavailable, and callers decide the fallback. None means the field
    itself is absent from both default/ and local/.
    """
    if not _HAS_SOLNLIB:
        msg = "solnlib is unavailable; cannot read geoip_settings.conf"
        raise RuntimeError(msg)
    conf = conf_manager.ConfManager(session_key, APP_NAME).get_conf(CONF_NAME)
    value: object | None = conf.get(stanza_name).get(field)
    return value


def get_configured_database_names(session_key: str) -> list[str]:
    """Get configured database names from geoip_databases.conf.

    Reads through solnlib with app_name pinned to the geoip app, like
    get_run_on_indexers_setting. Returns a possibly-empty list; callers
    decide whether an empty list is an error. The conf file not existing
    (it is only created when the first database is added) means the same
    as an empty one: nothing is configured.

    Raises on any other failure, including solnlib being unavailable (it
    is not part of the knowledge bundle, but the conf is only read on the
    search head); callers decide the fallback.
    """
    if not _HAS_SOLNLIB:
        msg = "solnlib is unavailable; cannot read geoip_databases.conf"
        raise RuntimeError(msg)

    cfm = conf_manager.ConfManager(
        session_key,
        APP_NAME,
    )
    try:
        conf = cfm.get_conf(f"{APP_NAME}_databases")
    except ConfManagerException:
        return []

    # Get all stanzas except 'default'
    return [name for name in conf.get_all(only_current_app=True) if name != "default"]


def has_account_credentials(session_key: str) -> bool:
    """Whether usable MaxMind credentials are configured, as a boolean only.

    Reads the account stanza of geoip_settings.conf through solnlib with
    the credential realm, like the updater's _get_account_credentials -
    solnlib needs the realm to decrypt the stanza's encrypted fields, and
    without it the read raises once credentials are saved (see
    SETTINGS_CREDENTIAL_REALM). The decrypted values only ever feed the
    boolean; they are never returned or logged.

    Applies validate_account_credentials - exactly the updater's
    acceptance checks - so a credential the updater rejects (say a typo'd
    account ID, which fails every update) does not report a clean bill of
    health.

    Raises on any failure, including solnlib being unavailable; callers
    decide the fallback. The account stanza always exists - the shipped
    default/geoip_settings.conf carries it with empty values - so a
    failed read means something is broken, not a fresh install.
    """
    if not _HAS_SOLNLIB:
        msg = "solnlib is unavailable; cannot read geoip_settings.conf"
        raise RuntimeError(msg)

    cfm = conf_manager.ConfManager(
        session_key,
        APP_NAME,
        realm=SETTINGS_CREDENTIAL_REALM,
    )
    stanza = cfm.get_conf(CONF_NAME).get("account", only_current_app=True)
    try:
        validate_account_credentials(
            stanza.get("account_id"),
            stanza.get("license_key"),
        )
    except ValueError:
        return False
    return True


def validate_account_credentials(
    account_id: str | None,
    license_key: str | None,
) -> tuple[int, str]:
    """Validate decrypted account values the way the updater accepts them.

    The one home of the acceptance policy (both values present, account
    ID numeric), so every reader of the account stanza agrees on what
    counts as usable credentials.

    Raises:
        ValueError: If a value is missing or the account ID is not a
            number, with a message telling the user what to fix.

    """
    if not account_id or not license_key:
        msg = (
            "MaxMind account credentials not configured. "
            "Go to Configuration > MaxMind Account to enter your credentials."
        )
        raise ValueError(msg)

    if not account_id.isdigit():
        msg = (
            f"MaxMind account ID must be a number, got '{account_id}'. "
            "Go to Configuration > MaxMind Account to correct your account ID."
        )
        raise ValueError(msg)

    return int(account_id), license_key


def get_fallback_logger() -> logging.Logger:
    """Get a basic logger for use when the configured logger is unavailable.

    Used when there is no session key, when get_logger's conf read fails,
    and by get_logger itself where solnlib is unavailable (every indexer).
    The log level is hardcoded to INFO since the user's configured level
    comes over Splunk's REST API - the thing that is missing or broken in
    all three cases.

    The logger gets a stderr handler if it has none, and stops propagating
    to the root logger. What the root logger does with a record depends on
    the process: the app's REST handler entry points give it only a
    NullHandler, so propagated records were discarded there - the whole
    reason this handler exists - while splunklib's searchcommands package
    gives it a stderr handler at import time, so propagation there would
    write every record twice. An own handler plus no propagation gives
    exactly one stderr copy in both; splunkd keeps stderr - search.log for
    search processes, splunkd.log otherwise. This is a different logger
    object from solnlib's, which is named after its log file path, not
    APP_NAME - so these records reach stderr only, never geoip.log. The
    handlers guard exists so repeated calls do not stack handlers.
    """
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


@lru_cache(maxsize=1)
def get_logger(session_key: str) -> logging.Logger:
    """Get a logger configured with the app's log level setting.

    The session key is required to read the user's configured log level
    from Splunk's REST API. Without it, the log level would be hardcoded
    and the Logging tab in the UI would have no effect.

    The result is cached to avoid repeated REST API calls. Only one logger
    is cached; concurrent searches with different session keys will evict
    each other's cached loggers, but this is acceptable since the log level
    setting is global anyway.
    """
    if not _HAS_SOLNLIB:
        return get_fallback_logger()

    logger: logging.Logger = solnlib_log.Logs().get_logger(APP_NAME)
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=APP_NAME,
        conf_name=CONF_NAME,
    )
    logger.setLevel(log_level)
    return logger
