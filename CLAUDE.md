# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

**Important**: When you learn something new about this project or make changes
that affect information documented here, update this file at the same time to
keep it accurate.

## Project Overview

This is a Splunk App for MaxMind GeoIP lookups, built using the Splunk UCC
(Universal Configuration Console) framework. It provides a custom streaming
search command (`geoip`) that enriches events with data from MaxMind databases
(country, city, anonymous IP, ISP, etc.), and a diagnostic generating command
(`geoipdebug`).

## The geoip Command

```spl
| geoip [prefix=<string>] [field=<string>] databases=<databases>
```

- `databases` (required): Comma-separated list of database names. **Must be
  quoted if multiple** (e.g., `databases="GeoIP2-Country,GeoIP2-Anonymous-IP"`)
- `field` (optional, default `ip`): Event field containing the IP address
- `prefix` (optional, default empty): Prefix for output field names

Behavior:

- Queries each database and merges all fields into the event
- When databases have conflicting fields, the last database wins
- The `network` field contains the most specific (smallest) CIDR block across
  all databases
- Database names are validated to only allow alphanumeric characters,
  underscores, and hyphens (security measure against path traversal)
- Events with missing, empty, invalid, or not-found IPs pass through unenriched
- Every event in a chunk carries the same field set (the union across the chunk,
  backfilled with empty values via `fill_missing_event_fields` in
  `geoip_utils.py`): the SDK's record writer locks the output fields to the
  first record's keys per chunk, so without this a pass-through event at the
  head of a chunk would silently strip the enrichment from every other event in
  it. `stream()` buffers one chunk (the SDK calls it once per SCP2 chunk) to
  compute the union.
- Runs on the search head by default; optionally on the indexers via the "Run on
  indexers" setting (see "Command distribution" below)

End-user documentation is in `README.md` (copied into the package by
`additional_packaging.py`).

### Command Architecture

The command implementation in `geoip_command.py` exposes
`stream(command, events)` and `prepare(command)` functions that the
UCC-generated wrapper calls (the wrapper's `prepare()` is injected by
`additional_packaging.py`). The `command` parameter follows a `Protocol` with:

- `databases`, `field`, `prefix` - command arguments
- `metadata.searchinfo.session_key` - Splunk session key for API calls (e.g.,
  reading settings)
- `metadata.searchinfo.app` - the app name
- `metadata.searchinfo.sid` - the search id (a `remote_` prefix identifies
  indexer invocations)
- `configuration.distributed` (prepare() only) - the SDK's runtime configuration

Database readers are cached at module level in `_readers`. This means:

- Databases are opened once and reused across events (good for performance)
- Splunk spawns a fresh Python process for each search, so the cache starts
  empty
- If the updater writes a new database file between searches, the next search
  automatically loads it

## The geoipdebug Command

```spl
| geoipdebug [indexers=<bool>]
```

A generating command (source `geoipdebug_command.py`, one event per item with a
`component` field) that reports diagnostic information so users can see which
database versions a node uses (GitHub #76) and send us a support baseline:

- `component=database`: one event per configured database (from
  `geoip_databases.conf` via `get_configured_database_names`) with `present`,
  `build_time` (mmdb metadata `build_epoch`, RFC 3339 UTC), `database_type`, and
  file path/size/mtime. A search-head run first migrates legacy databases (like
  the geoip command on a miss), so an upgrade does not show them as absent. On
  an indexer - or if the conf read fails - it lists the `*.mmdb` files in the
  database directory instead, which on an indexer is what the knowledge bundle
  carries. `database_source` (`configured`/`directory`) says which of the two
  produced the event, and configured names get the same `is_valid_database_name`
  guard as the geoip command before becoming paths.
- `component=system`: app version (parsed from `default/app.conf`, where UCC
  writes it at build time; `build.sh` verifies the built file has the key, since
  the source tree's does not and tests monkeypatch the path), Splunk version
  (from `searchinfo.splunk_version`), Python version, database directory,
  `on_indexer`.
- `component=settings` (search head only): `loglevel` (the raw configured value
  via `get_setting`, deliberately not solnlib's `get_log_level`, which swallows
  failed reads into the INFO default), `run_on_indexers`, configured database
  list, and `credentials_configured` as a boolean - the credential values are
  read (decrypted) only inside `has_account_credentials` to compute it and are
  never output. UCC ships `default/geoip_settings.conf` (generated from the
  globalConfig defaults: loglevel INFO, run_on_indexers 0, an empty account
  stanza) and the conf endpoint merges default/ and local/, so settings reads
  find values on any healthy install; a failed read is a fault and reports
  `unknown`. Boolean event fields are emitted as the strings true/false via
  `_bool_text` - the SDK writes Python bools as 1/0, and mixed with `unknown`
  the field would have no stable type.

Every event carries `hostname`; nothing takes the search down (a broken database
gets an `error` field, a failed settings read `unknown`).

Two behaviors verified on a live cluster:

- With `indexers=true` the command runs on the search head AND on each search
  peer - the results merge both, distinguished by `hostname`. On a peer it emits
  its system event and one database event per `.mmdb` in the bundle (none while
  "Run on indexers" is off), and no settings event.
- The SDK's record writer locks the output field set to the keys of the first
  record in each output chunk (splunklib `internals.RecordWriter._write_record`;
  `RecordWriterV2._clear` resets it per chunk), so `generate()` fills every
  event with the union of all events' fields via `fill_missing_event_fields`
  (shared with the geoip command's `stream()`) - without that, the components
  emitted after the first silently lose the fields the first does not have.

Distribution is decided by the command's own `indexers` argument (default false
= search-head-only), not the "Run on indexers" setting: `prepare()` in
`geoipdebug_command.py` sets `configuration.distributed` from the parsed option
(the SDK parses arguments before calling `prepare()`), with no REST read. Note
`GeneratingCommand` differs from `StreamingCommand` here: its SCP2 `distributed`
already defaults to False, so the `@Configuration(distributed=False)` the
packaging hook writes is belt-and-braces, not load-bearing.

The command name has no underscore because UCC validates `commandName` against
`^[a-z0-9]+$` (and requires it to differ from `fileName` minus `.py`).

## Database Storage and Updates

### Storage Location

Databases are stored in the app's `databases/` directory, resolved relative to
`lib/geoip_utils.py` (not via `$SPLUNK_HOME`):

- A custom app-level directory is outside search head cluster conf replication
  summaries (which capture only `local/...`, `lookups/*`, and metadata) and
  outside Splunk's default knowledge bundle allowlist (app `bin/` and
  `lookups/`), so whether the databases replicate anywhere is controlled
  entirely by the app's own `distsearch.conf` allowlist entry - and no
  `conf_replication_summary` excludelist in `server.conf`, which AppInspect
  rejects, is needed to keep them out of SHC baselines
- The relative resolution works both when the app is installed
  (`etc/apps/geoip/`) and when it runs from a knowledge bundle on an indexer
  (`var/run/searchpeers/<bundle>/apps/geoip/`)

For testing, set the `MAXMIND_DB_DIR` environment variable to override the
database directory.

### Migration from the pre-1.2.0 location

`migrate_legacy_databases` (geoip_utils.py) moves anything left in the old
location (`local/data/`, resolved via `$SPLUNK_HOME`) into `databases/`. It runs
at the start of every updater run (even unconfigured), when the geoip command
misses a database on the search head, and at the start of every search-head
`geoipdebug` run (so it does not report a not-yet-migrated database as absent) -
never on an indexer, where the app runs from the knowledge bundle. Once the old
directory is gone it is a single `stat()` no-op. The move is link-then-unlink,
which never overwrites: a file already in `databases/` is a fresher download, so
the legacy copy is just deleted. It also never raises - searches and update runs
must survive a failed migration. Residual gap: on Splunk Cloud Victoria only one
SHC member runs the input (GitHub #76), so a member that neither runs the input
nor serves a `geoip` search keeps its legacy files indefinitely.

### Automatic Updates

The `geoipupdate_input` modular input downloads and updates databases
automatically:

- A default input (`geoipupdate_input://default`) is enabled out of the box (no
  UI, runs in background)
- Users configure their MaxMind credentials and add databases to download
- Updates only run when credentials AND at least one database are configured
- Uses the `pygeoipupdate` PyPI package
- Default update interval is 3600 seconds (1 hour)
- `run_only_one = false` in `inputs.conf` is intended to make each Search Head
  Cluster member download its own databases, but on Splunk Cloud Victoria only
  one member runs the input (GitHub #76, unresolved); the 1.1.3 scripted-input
  experiment did not fix this either

The input gracefully handles incomplete configuration - it logs a warning and
skips the update until both credentials and databases are configured.

Before the configuration checks, every run also migrates legacy databases and
syncs the knowledge bundle state marker
(`_sync_replication_marker_from_settings`, see "Command distribution" below) -
both must happen even while the updater is unconfigured.

#### Modular Input Registration

Splunk discovers modular input types by reading `README/inputs.conf.spec`. Two
requirements:

1. **The spec must have at least one custom parameter** (even a dummy
   `param1 =`) or Splunk's `SpecFiles` silently ignores the input type entirely.
2. **`use_single_instance` must be `False`** in the scheme for interval-based
   scheduling to work. With `True`, Splunk runs the script once at startup but
   does not re-run it on the configured interval.

### pygeoipupdate Library

The app depends on the `pygeoipupdate` PyPI package (listed in
`package/lib/requirements.txt`). This async library handles:

- MaxMind API authentication
- Database download with retry logic
- Atomic file writes with hash verification
- File locking to prevent concurrent updates

## Build Commands

```bash
# Setup environment
mise install                      # Install uv, precious
uv sync --group lint              # Install build and lint dependencies
git submodule update --init       # Initialize test data submodule

# Build the app
./build.sh      # Generates output/ directory and .tar.gz package

# Run tests
uv run pytest tests

# Lint
precious lint -g

# Format (tidy)
precious tidy -g

# Splunk Cloud compatibility check (run after build)
precious lint --command appinspect geoip-1.1.0.tar.gz

# Install to Splunk (requires Splunk 10.2)
splunk install app /path/to/geoip-1.1.0.tar.gz
splunk install app /path/to/geoip-1.1.0.tar.gz -update true  # Update existing
```

## Tests

Tests live in `tests/` and use pytest. Test data comes from the `MaxMind-DB` git
submodule at `tests/data/`.

The `MAXMIND_DB_DIR` environment variable overrides the database directory,
allowing tests to use test databases from the MaxMind-DB submodule instead of
production databases.

The `GEOIP_LOOKUPS_DIR` environment variable similarly overrides the lookups
directory holding the knowledge bundle state marker; an autouse conftest fixture
points it at a per-test tmp_path so tests never write into the repo's package
tree.

Test IPs from GeoIP2-Country-Test.mmdb:

- `214.78.120.1` (in `214.78.120.0/22`) → US
- `2001:218::1` (in `2001:218::/32`) → JP
- `2001:220::1` (in `2001:220::1/128`) → KR

For multi-database testing, `89.160.20.112` is useful as it exists in multiple
test databases:

- GeoIP2-Country-Test (`/28`) → SE
- GeoIP2-City-Test (`/28`) → SE, Linköping
- GeoIP2-ISP-Test (`/29`) → Linköping Universitet

This IP is good for testing field merging and smallest-network selection.

## Linting

Uses ruff (linting + formatting) and mypy (type checking) for Python, and
prettier for Markdown, orchestrated via precious (`precious lint -g`).

The prettier setup mirrors our other repos (geoipupdate, mmdbconvert,
mmdbinspect, and others): mise installs node and prettier, `.prettierrc.json`
sets `proseWrap: always` with an 80 column width, and a `prettier-markdown`
command in `.precious.toml` checks (`--check`) or rewrites (`--write`) every
`*.md` file. The `tests/data` submodule is excluded - it is MaxMind-DB, not ours
to reformat. Note that prettier rewrites `*` bullets as `-` and pads table cells
to align.

For Splunk Cloud compatibility, use `splunk-appinspect` to validate the built
package:

```bash
precious lint --command appinspect geoip-1.1.0.tar.gz
```

This runs AppInspect with the `cloud` tag to check for Splunk Cloud deployment
requirements. The tarball is gitignored, so this must be run explicitly after
building (not included in `precious lint -g`). The `Lint` GitHub Actions
workflow builds the package and runs this same command, so its tarball version
must be kept in step with `build.sh` (`dev-bin/release.sh` updates both).

`splunk-appinspect inspect` exits 0 even when checks fail - the failure count
only shows up in the report summary it prints. The `--ci` flag in
`.precious.toml` makes it exit 101 for failures, 104 for future failures, and
103 for warnings instead; without `--ci`, both the local command and CI silently
pass on any AppInspect failure. `ok-exit-codes` is `[0, 103]` because the
vendored third-party libraries trip several warnings that cannot be fixed here;
101 and 104 are `lint-failure-exit-codes` (failure shown with the report); and
appinspect's 1 (a check errored), 2 (run-time error), and 3 (unopenable package)
are deliberately in neither list - precious fails on any exit code it was not
told about, dumping the output. Verified end to end: a
`conf_replication_summary` key in `server.conf` turns the linter red with the
failing check in the report. One tradeoff: precious discards output on ok exit
codes, so a passing run shows nothing, warnings included - to read them, run
`uv run splunk-appinspect inspect <tarball> --mode precert --included-tags cloud`
directly.

## Key Configuration Files

### globalConfig.json

The main UCC configuration file. Defines:

- Configuration tabs (account, databases, distribution, logging)
- Custom search commands (use `defaultValue` not `default` for argument
  defaults)
- UI settings

#### Configuration Tab Types

Tabs in `pages.configuration.tabs` can be either **multi-instance tables** or
**single-instance forms**:

**Multi-instance table** (for multiple accounts/configurations, e.g. the
databases tab):

- Has `table` property with actions and header columns
- Requires a `name` field to identify each instance
- UI shows a table with add/edit/delete actions

**Single-instance form** (for one set of settings, e.g. the account tab):

- No `table` property
- No `name` field needed
- UI shows a simple form with save button

#### Field Encryption

Use `"encrypted": true` on sensitive fields (API keys, passwords). UCC stores
these in Splunk's secure credential storage (`passwords.conf`) rather than plain
text config files.

### package/app.manifest

JSON file with app metadata. Note: The `version` field here should match
`globalConfig.json` for consistency, but UCC uses the version from
`globalConfig.json` as the source of truth and overwrites `app.manifest` during
build.

### package/default/app.conf

Custom settings merged into the generated `app.conf`. Example:

```ini
[launcher]
author = MaxMind
```

### package/default/commands.conf

Custom search command configuration. Unlike `app.conf`, UCC **replaces** (not
merges) this file, so you must include all required settings:

```ini
[geoip]
filename = geoip.py
chunked = true
local = true
python.version = python3
python.required = 3.13

[geoipdebug]
filename = geoipdebug.py
chunked = true
python.version = python3
python.required = 3.13
```

A command in `globalConfig.json` with no stanza here is silently unregistered;
`tests/commands_conf_test.py` guards the two files against drift.

- `chunked = true` is required for streaming and generating commands using the
  Splunk SDK
- `local = true` is an SCP1-only setting and is **ignored** for chunked (SCP2)
  commands. It is left in as a harmless fallback, but it does **not** keep the
  command on the search head. See "Command distribution" below for what actually
  works.
- `python.version` is for backward compatibility with Splunk < 10.2
- `python.required` is used by Splunk 10.2+ (takes precedence over
  `python.version`)

#### Command distribution ("Run on indexers")

Under SCP2 (`chunked = true`), Splunk decides distribution from the command's
getinfo response, not `commands.conf`. The Splunk SDK defaults to reporting
distributable streaming (`type = streaming`); `distributed=False` makes it
report `type = stateful` (search-head-only, the built-in equivalent of
`| localop`). You cannot set `type = stateful` directly in the decorator -
`StreamingCommand` declares `type` read-only at `streaming`, and the SDK
rewrites it to `stateful` only as it emits the metadata, only when `distributed`
is false.

Distribution is decided per search by `prepare()` in `geoip_command.py`, which
the SDK calls before writing the getinfo reply:

- On the search head, it sets `configuration.distributed` from the "Run on
  indexers" setting (`[distribution] run_on_indexers` in `geoip_settings.conf`),
  defaulting to search-head-only on any failure. The read goes through solnlib
  pinned to the geoip app's namespace (`get_run_on_indexers_setting`), like
  `get_logger` - not through `command.service`, which is namespaced to the
  dispatching app and only resolves the conf via the app's `export = system`
  metadata.
- On an indexer (search ids there carry a `remote_` prefix), it reports
  distributed streaming and never touches REST - the app's conf endpoints do not
  exist on peers, where the app runs from the knowledge bundle under
  `var/run/searchpeers/`, not `etc/apps/`.

UCC has no globalConfig knob for any of this and its custom-command templates
hardcode `@Configuration()` with no extension point, so the post-build hook in
`additional_packaging.py` (`make_command_distribution_toggleable`) rewrites the
generated wrappers (`bin/geoip.py` and `bin/geoipdebug.py`): it imports
`prepare` from the command's source module, injects a `prepare()` method, and
changes the decorator to `@Configuration(distributed=False)` as a fail-safe
default in case `prepare()` somehow does not run. The command list comes from
`globalConfig.json` (commandType picks the entry point to wrap), so a command
added there cannot ship without the rewrite. The hook raises if any marker is
missing, so a UCC template change fails the build loudly rather than silently
regressing; `build.sh` re-checks the markers as a backstop because UCC swallows
`ImportError` from the hook.

### package/default/distsearch.conf and server.conf

What reaches the indexers is controlled by `default/distsearch.conf`:

- Splunk's default replication allowlist covers app `bin/` and `lookups/`
  directories plus `.conf`/`.meta` files, but NOT `lib/`. The app adds allowlist
  entries for the minimal set the command imports at search time on an indexer:
  `lib/splunklib`, `lib/maxminddb*` (the `*` also matches the
  `maxminddb-<version>.dist-info` directory, which maxminddb reads at import
  time via `importlib.metadata.version()` - without it the command crashes on
  the indexer), and `lib/geoip_utils.py` (about 0.9 MB total). The remaining
  vendored libraries (grpc, aiohttp, opentelemetry, ...; about 35 MB) are
  download-only dependencies and stay out of the bundle.
  `geoip_utils.get_logger` falls back to a basic logger on indexers where
  solnlib is unavailable.
- The databases live in the app's `databases/` directory, which is not in
  Splunk's default allowlist, so while the toggle is off nothing there (the
  databases, the updater's in-progress `*.temporary` downloads, its lock file)
  rides the bundle at all. The `geoip_mmdb` allowlist key ships as a placeholder
  that matches no real file - deliberately not an empty value, which in an
  allowlist matches everything. Saving "Run on indexers" overrides it in
  `local/distsearch.conf` (see `_apply_mmdb_replication` in
  `geoip_rh_settings.py`): the real `apps/geoip/databases/*.mmdb` pattern when
  enabled, the placeholder when disabled (conf keys cannot be deleted through
  the REST API). With the toggle on, the scratch files stay out for a different
  reason: pygeoipupdate names in-progress downloads
  `<edition>_<random>.temporary`, which `*.mmdb` does not match.
- IMPORTANT restart semantics (verified on a live cluster): splunkd only reads
  the replication allowlist/denylist at startup, so toggling the setting changes
  bundle content only after the search head restarts. The command's
  `distributed` flag, read per search in `prepare()`, switches immediately - so
  in a distributed deployment, geoip searches fail with the missing-database
  error between enabling and the first bundle push after the restart (disabling
  is safe immediately). On a single instance with no search peers, distributing
  changes nothing and nothing fails (deliberately not mentioned in the README,
  which discusses the toggle only in replication terms). New or updated database
  files under unchanged rules enter the bundle automatically within a bundle
  cycle or two - no restart. The help text, README, and the missing-database
  error all reflect the restart timing.
- A restart is necessary but NOT sufficient (verified on a live cluster,
  2026-08-20): Splunk identifies a bundle by a checksum over its file metadata,
  and when the rebuilt bundle's checksum matches a bundle a peer already holds
  in its inventory (`services/admin/bundles`), the push is skipped as
  `already_present` and the peer's latest common bundle never advances - the
  toggle then silently never takes effect on the peers, in either direction,
  until an unrelated allowlisted file changes. Toggling flips the bundle between
  two recurring states, so on a quiet cluster the second and later toggles in
  each direction hit this. The fix is the bundle state marker
  `lookups/geoip_replication_state.csv` (`sync_replication_marker` in
  `geoip_utils.py`): it records the toggle state in an always-replicated file
  (lookups/ is in Splunk's default bundle allowlist), so every state change
  rewrites the file and the fresh mtime gives the next bundle a checksum no peer
  has seen - the checksum covers file metadata, so the mtime is the whole
  mechanism. lookups/ is also in SHC replication summaries (the reason the
  databases avoid it), which is harmless for a few-byte file whose content every
  member derives from the same replicated setting - direct disk writes are not
  journaled, so each member maintains its own copy. Written by the settings
  handler on save (a pre-restart write suffices - the fresh mtime rides into the
  post-restart bundle) and synced by the updater input each run, which covers
  members that did not serve the save. Residual gap: on Splunk Cloud Victoria
  only one SHC member runs the input (GitHub #76), so a captain that neither
  runs the input nor serves the save keeps a stale marker - narrowed by a third
  writer: the geoip command's `prepare()` also syncs the marker on a successful
  settings read, so such a captain unsticks when it next dispatches a geoip
  search. For testing, the `GEOIP_LOOKUPS_DIR` environment variable overrides
  the marker's directory, like `MAXMIND_DB_DIR` for the databases. Diagnostics:
  `index=_internal group=bundles_uploads name=peer_dispatch`
  (`status=already_present` is the stuck signature) and
  `group=bundle_replication name=common_bundle_status`
  (`latest_common_bundle_checksum` advances only on a real upload).

Bundle pushes are triggered by searches dispatched to the indexers, and the
triggering search still runs against the previous bundle - hence the tailored
"Database not found on this indexer" error in `geoip_command.py` explaining the
first-search timing. There is no silent fallback to the search head: pipeline
placement is fixed at parse time, and yielding events unenriched would silently
produce wrong results.

`default/server.conf` must be maintained by hand because UCC skips generating it
when the package ships one. It replicates the app's custom conf files and
`distsearch.conf` across search head cluster members (so the toggle's local
override reaches all of them; verified live - splunkd honours
`conf_replication_include` for a conf type absent from its default list, and
both `local/distsearch.conf` and `local/geoip_settings.conf` reached the
non-captain member). `conf_replication_include.distsearch` is instance-wide, not
app-scoped: `[shclustering]` keys from every app merge into one effective
`server.conf`, so it enables replication of every runtime `distsearch.conf`
change on the members, `etc/system/local` and other apps' included - which
matters because `distsearch.conf` can carry member-specific settings
(`[distributedSearch] servers`/`disabled`, `[replicationSettings]`,
`[tokenExchKeys] certDir`, `genKeyScript`). There is no app-scoped alternative;
the include list is keyed by conf name. It needs no `conf_replication_summary`
keys - and AppInspect rejects them in an app's server.conf - because the
`databases/` directory is outside the SHC replication summary entirely. That
matters: members each download their own copies (direct disk writes are not
journaled, so they never replicate between members in steady state anyway), and
a destructive resync (`splunk resync shcluster-replicated-config`) was verified
live to rewrite summarized files from the captain's baseline IN PLACE (same
inode, new mtime) - a concurrent search reading a database mid-resync could see
inconsistent data. Keeping the databases out of the summary makes the updater's
atomic temp-file-and-rename write the only way they are ever written.
`tests/server_conf_test.py` and `tests/distsearch_conf_test.py` guard these
files against drift.

### Splunk path patterns in conf files

The path patterns in conf files like `distsearch.conf`'s
`[replicationAllowlist]`/`[replicationDenylist]` stanzas use Splunk's pattern
language (the "match language" in `props.conf.spec`), not plain regexes: `...`
matches anything, `*` matches anything except `/`, `|` and `()` work as in
regexes, and **a dot matches a literal dot** - never escape it. Splunkd escapes
dots itself, so a hand-written `\.` becomes a match for backslash-then-dot and
the pattern silently matches nothing (verified on a live cluster: a replication
rule ending `\.mmdb` left the file in the knowledge bundle; the unescaped
pattern removed it). Splunk's own defaults never escape dots, e.g. `*.conf`,
`....pyc$`, `lookups/*.(tmp$|index((|.alive|.lock)$|/...))`.

## Dependencies

There are three places where dependencies are managed:

- **Dev tools**: `mise.toml` - uv, precious, node and prettier (managed by
  mise); Python is managed by uv
- **Build/dev dependencies**: `pyproject.toml` - pytest, mypy, ruff, UCC
  framework (managed by uv)
- **App runtime dependencies**: `package/lib/requirements.txt` - splunktaucclib,
  splunk-sdk, solnlib, maxminddb, pygeoipupdate (installed into app's lib/ at
  build time)

### Updating Dependencies

To update all dependencies, use the `update-deps` skill
(`.claude/skills/update-deps/SKILL.md`). Dependabot already covers
`pyproject.toml`/`uv.lock` (the `uv` ecosystem) and
`package/lib/requirements.txt` (the `pip` ecosystem); nothing covers
`mise.toml`, so the mise tools are the part to bump by hand.

**Important**: Keep Python on 3.13.x as that is the latest major version Splunk
supports. When updating `maxminddb`, `pygeoipupdate`, or `solnlib` in both
`pyproject.toml` (dev) and `requirements.txt` (runtime), ensure versions stay in
sync (`solnlib` is pinned `==` in both so the import-surface test guards the
shipped version). `tests/requirements_test.py` enforces this: every
`requirements.txt` pin that `uv.lock` also resolves must be the locked version,
so a Dependabot `uv` PR that bumps one of them goes red until `requirements.txt`
is bumped in the same change. That guard matters because the `pip` Dependabot
job for `requirements.txt` would otherwise be unable to bump `solnlib`: with no
Python version declared in its directory, the job assumes the newest Python
Dependabot ships (3.14.x), and `solnlib` requires `<3.14`.
`geoip/package/lib/.python-version` exists to fix that (the pip job reads the
file from its own directory, then falls back to the repo root). It must hold a
full `3.13.x` - Dependabot only accepts a value that appears verbatim in
`pyenv install --list`, which has no bare `3.13`, so a two-part version is
silently ignored. The patch number is otherwise irrelevant (Dependabot coerces
it to a wildcard) and Dependabot never bumps this file itself. It lives under
`package/lib/` rather than the repo root so uv does not see it (uv would pin the
interpreter to that exact patch); `build.sh` deletes it from `output/` because
dotfiles are prohibited in Splunk Cloud apps. `tests/requirements_test.py`
checks its format.

## UCC Framework Behavior

- UCC generates `.conf` files in the output `default/` directory
- For `app.conf`: UCC merges your settings with generated ones
- For `commands.conf`: UCC **replaces** the generated file entirely with yours
  (include all required settings)
- UCC automatically sets `python.version = python3` in generated `commands.conf`
  and `inputs.conf`
- Warning about "not auto generated by UCC framework" for custom settings is
  expected
- `ucc-gen init` creates a `README.md` in the app source directory, but it's not
  needed and doesn't get included in the output package. Use `package/README.md`
  for end-user documentation instead.
- `additional_packaging.py` is a UCC post-build hook called by `ucc-gen build`.
  It copies `LICENSE-MIT` and `LICENSE-APACHE` from the repo root into
  `output/geoip/LICENSES/`, and `README.md` into `output/geoip/`. It also
  rewrites the generated command wrappers (`bin/geoip.py`, `bin/geoipdebug.py`)
  to inject a `prepare()` method and a fail-safe `distributed=False` default
  (see "Command distribution").

### Custom Search Command File Naming

UCC generates a wrapper script for custom search commands. The naming works as
follows:

- `globalConfig.json` specifies `commandName` (e.g., `"geoip"`) and `fileName`
  (e.g., `"geoip_command.py"`)
- UCC generates a wrapper named `<commandName>.py` (e.g., `geoip.py`) that
  imports from your `fileName`
- `commands.conf` must reference the **wrapper** name (`filename = geoip.py`),
  not the source file

The generated wrapper (`output/.../bin/geoip.py`) looks like:

```python
from geoip_command import stream

class GeoipCommand(StreamingCommand):
    def stream(self, events):
        return stream(self, events)
```

So the source file (`geoip_command.py`) and wrapper (`geoip.py`) are
intentionally different files.

UCC validates `commandName` against `^[a-z0-9]+$` (no underscores, hyphens, or
uppercase) and requires it to differ from `fileName` minus `.py` - hence
`geoipdebug` with source `geoipdebug_command.py`.

### Custom REST Handlers

Custom REST handlers allow you to add logic when configuration is saved. We use
this to trigger background database updates when users save credentials or add
databases.

**How it works:**

UCC generates REST handler files (`geoip_rh_*.py`) that handle API requests for
configuration tabs. You can customize these handlers to add pre/post-save logic.

**For multi-instance tables** (like the databases tab), use `restHandlerModule`
and `restHandlerClass` in `globalConfig.json`:

```json
{
    "name": "databases",
    "table": {...},
    "entity": [...],
    "restHandlerModule": "geoip_handler",
    "restHandlerClass": "GeoipDatabasesHandler"
}
```

UCC generates a wrapper (`geoip_rh_databases.py`) that imports your class from
`geoip_handler.py` and uses it as the handler. Your module only needs the
handler class - UCC generates the endpoint/field definitions.

**For single-instance forms** (like the account tab),
`restHandlerModule`/`restHandlerClass` don't work. You must provide the complete
handler file (`geoip_rh_settings.py`) with:

- Field definitions (duplicated from `globalConfig.json`)
- Endpoint setup (`MultipleModel`)
- Custom handler class

This duplication is unavoidable - UCC either generates the entire file OR copies
yours; it can't merge them.

**Files involved:**

| File                    | Purpose                                                                                                                                                                                       |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `geoip_handler.py`      | Shared module with `GeoipDatabasesHandler` class and background update functions                                                                                                              |
| `geoip_rh_settings.py`  | Complete custom handler for account/distribution/logging settings (field definitions duplicated); also writes the distsearch.conf override and the bundle state marker for the indexer toggle |
| `geoip_rh_databases.py` | UCC-generated wrapper that imports `GeoipDatabasesHandler`                                                                                                                                    |

**Handler class pattern:**

```python
class GeoipDatabasesHandler(AdminExternalHandler):
    def handleEdit(self, confInfo):
        AdminExternalHandler.handleEdit(self, confInfo)  # Do the save
        trigger_background_update(self.getSessionKey())  # Custom logic

    def handleCreate(self, confInfo):
        AdminExternalHandler.handleCreate(self, confInfo)
        trigger_background_update(self.getSessionKey())
```

**Important:** Don't call `util.remove_http_proxy_env_vars()` in custom handlers
if you need proxy support for external API calls (like downloading from
MaxMind).

## Splunk Python Version Configuration

In Splunk 10.2+, `python.version` is deprecated. Use `python.required` instead:

- `python.required = 3.13` uses just the version number (not "python3.13")
- Default `python.version = python3` resolves to Python 3.9 in Splunk 10.2, not
  the latest
- Include both settings for backward compatibility with older Splunk versions
- The `maxminddb` 3.0.0 package requires Python 3.10+ (uses `kw_only` in
  dataclasses)

## Reinstalling the App

When reinstalling, fully remove the old app first to avoid cached libraries:

```bash
splunk remove app geoip
splunk restart
splunk install app /path/to/geoip-1.1.0.tar.gz
```

## Logging

Logging uses solnlib to write to
`$SPLUNK_HOME/var/log/splunk/{logger_name}.log`. The log level is configured via
the Logging tab in the app's UI.

`geoip_utils.py` provides three logger helpers:

- `get_logger_or_fallback(session_key)` is what callers should use: the
  configured logger, degrading to the fallback instead of raising when the log
  level read fails. It is the one home of that guard, so no caller re-implements
  it. It carries its own `@lru_cache(maxsize=1)` because `get_logger`'s cache
  does not cover the raising case (`lru_cache` does not cache exceptions) -
  without it, a broken node would re-attempt the REST read and log another
  traceback on every call.
- `get_logger(session_key)` builds the configured logger and raises when the
  conf read fails; only for a caller that wants the failure. Decorated with
  `@lru_cache(maxsize=1)` to avoid repeated REST API calls to read the log level
  setting.
- `get_fallback_logger()` is for when there is no session key at all.

`get_fallback_logger()` (also used when `get_logger`'s REST read fails) is a
different logger object from solnlib's, which is named after its log file path:
fallback records go to stderr only - search.log for search processes,
splunkd.log otherwise - and never to `geoip.log`. It carries its own stderr
handler with `propagate = False`, so records print exactly once whether the
process gave the root logger a NullHandler (the app's REST handlers) or a stderr
handler (splunklib's searchcommands import).

### Key Points

- **Log file location**: `$SPLUNK_HOME/var/log/splunk/{logger_name}.log` - use
  the app name as logger name for consistency
- **Session key**: Required to read log level from settings. Available via
  `command.metadata.searchinfo.session_key` in streaming commands
- **Caching**: The logger is cached with `lru_cache` so only the first call per
  process makes a REST API call. Only one entry is cached; concurrent searches
  with different session keys evict each other, which is fine since the log
  level is global
- **Logging tab**: Add `{"type": "loggingTab"}` to `globalConfig.json`
  configuration tabs. Settings are stored in `{app_name}_settings.conf` under
  the `[logging]` stanza with a `loglevel` field
- **Don't use `set_context(namespace=...)`**: This prefixes the log filename,
  resulting in `{namespace}_{logger_name}.log` instead of just
  `{logger_name}.log`

## Key Constraints

- Always run tidying (`precious tidy -g`), linters (`precious lint -g`), tests
  (`uv run pytest tests`), and `./build.sh` before considering any changes
  complete
- The `author` field in `package/default/app.conf` must exactly match the first
  author name in `package/app.manifest`
