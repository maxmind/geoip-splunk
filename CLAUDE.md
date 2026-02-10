# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Important**: When you learn something new about this project or make changes that affect information documented here, update this file at the same time to keep it accurate.

## Project Overview

This is a Splunk Add-on for MaxMind GeoIP lookups, built using the Splunk UCC (Universal Configuration Console) framework. It provides a custom streaming search command (`geoip`) that enriches events with data from MaxMind databases (country, city, anonymous IP, ISP, etc.).

## The geoip Command

```
| geoip [prefix=<string>] [field=<string>] databases=<databases>
```

- `databases` (required): Comma-separated list of database names. **Must be quoted if multiple** (e.g., `databases="GeoIP2-Country,GeoIP2-Anonymous-IP"`)
- `field` (optional, default `ip`): Event field containing the IP address
- `prefix` (optional, default empty): Prefix for output field names

Behavior:
- Queries each database and merges all fields into the event
- When databases have conflicting fields, the last database wins
- The `network` field contains the most specific (smallest) CIDR block across all databases
- Database names are validated to only allow alphanumeric characters and hyphens (security measure against path traversal)
- Events with missing, empty, invalid, or not-found IPs pass through unchanged

End-user documentation is in `README.md` (copied into the package by `additional_packaging.py`).

### Command Architecture

The command implementation in `geoip_command.py` exposes a `stream(command, events)` function that the UCC-generated wrapper calls. The `command` parameter follows a `Protocol` with:
- `databases`, `field`, `prefix` - command arguments
- `metadata.searchinfo.session_key` - Splunk session key for API calls (e.g., reading settings)
- `metadata.searchinfo.app` - the app name

Database readers are cached at module level in `_readers`. This means:
- Databases are opened once and reused across events (good for performance)
- Splunk spawns a fresh Python process for each search, so the cache starts empty
- If the updater writes a new database file between searches, the next search automatically loads it

## Database Storage and Updates

### Storage Location

Databases are stored at `$SPLUNK_HOME/etc/apps/geoip/local/data/`:
- The `/local/` directory is preserved across add-on upgrades
- Apps can write to their own `/local/` directory in both Enterprise and Cloud
- The `/data/` subdirectory keeps databases separate from .conf files

For testing, set the `MAXMIND_DB_DIR` environment variable to override the database directory.

### Automatic Updates

The `geoipupdate_input` modular input downloads and updates databases automatically:
- A default input (`geoipupdate_input://default`) is enabled out of the box (no UI, runs in background)
- Users configure their MaxMind credentials and add databases to download
- Updates only run when credentials AND at least one database are configured
- Uses the vendored `geoipupdate` library in `package/lib/geoipupdate/`
- Default update interval is 3600 seconds (1 hour)
- `run_only_one = false` in `inputs.conf` ensures each node in a Search Head Cluster downloads its own databases

The input gracefully handles incomplete configuration - it logs a warning and skips the update until both credentials and databases are configured.

#### Modular Input Registration

Splunk discovers modular input types by reading `README/inputs.conf.spec`. Two requirements:

1. **The spec must have at least one custom parameter** (even a dummy `param1 =`) or Splunk's `SpecFiles` silently ignores the input type entirely.
2. **`use_single_instance` must be `False`** in the scheme for interval-based scheduling to work. With `True`, Splunk runs the script once at startup but does not re-run it on the configured interval.

### geoipupdate Library

The add-on includes a vendored copy of the geoipupdate Python library at `package/lib/geoipupdate/`. This async library handles:
- MaxMind API authentication
- Database download with retry logic
- Atomic file writes with hash verification
- File locking to prevent concurrent updates

## Build Commands

```bash
# Setup environment
mise install                      # Install Python, uv, precious
uv sync                           # Install build dependencies
git submodule update --init       # Initialize test data submodule

# Build the add-on
./build.sh      # Generates output/ directory and .tar.gz package

# Run tests
uv run pytest tests

# Lint
precious lint -g

# Format (tidy)
precious tidy -g

# Splunk Cloud compatibility check (run after build)
precious lint --command appinspect geoip-1.0.0.tar.gz

# Install to Splunk (requires Splunk 10.2)
splunk install app /path/to/geoip-1.0.0.tar.gz
splunk install app /path/to/geoip-1.0.0.tar.gz -update true  # Update existing
```

## Project Structure

```
CHANGELOG.md                  # Release history
.github/
├── dependabot.yml            # Automated dependency updates
└── workflows/
    ├── codeql-analysis.yml   # CodeQL security scanning
    ├── lint.yml              # Formatting, linting, and AppInspect
    ├── test.yml              # pytest on Ubuntu
    └── zizmor.yml            # GitHub Actions security audit
geoip/
├── globalConfig.json         # Main configuration file for UCC framework
├── additional_packaging.py   # UCC post-build hook (copies licenses/README)
├── package/
│   ├── app.manifest          # Add-on metadata (author, version, description)
│   ├── README.md             # End-user documentation (included in package)
│   ├── LICENSES/             # License files included in package
│   ├── default/
│   │   ├── app.conf          # Splunk app configuration (merged with generated)
│   │   ├── commands.conf     # Search command configuration (replaces generated)
│   │   └── inputs.conf       # Modular input configuration (replaces generated)
│   ├── bin/                  # Python scripts (inputs, custom commands)
│   │   ├── geoip_command.py       # The geoip search command
│   │   ├── geoip_handler.py       # Custom REST handler for databases tab
│   │   ├── geoip_rh_settings.py   # Custom REST handler for account/logging
│   │   └── geoipupdate_input.py   # Database update modular input
│   ├── lib/
│   │   ├── geoip_utils.py   # Shared utilities (logging, paths, constants)
│   │   ├── requirements.txt  # Python dependencies for the add-on
│   │   └── geoipupdate/      # Vendored geoipupdate library
│   └── static/               # Icons and images
```

## Tests

Tests live in `tests/` and use pytest. Test data comes from the `MaxMind-DB` git submodule at `tests/data/`.

```
tests/
├── conftest.py                  # Sets MAXMIND_DB_DIR to test database directory
├── data/                        # MaxMind-DB submodule (git submodule)
│   └── test-data/               # Contains test .mmdb files
├── geoip_command_test.py        # Tests using various test databases
├── geoip_handler_test.py        # Tests for REST handler (databases tab)
├── geoip_rh_settings_test.py    # Tests for REST handler (account/logging)
├── geoip_utils_test.py          # Tests for shared utility functions
└── geoipupdate_input_test.py    # Tests for database update functionality
```

The `MAXMIND_DB_DIR` environment variable overrides the database directory, allowing tests to use test databases from the MaxMind-DB submodule instead of production databases.

Test IPs from GeoIP2-Country-Test.mmdb:
- `214.78.120.1` (in `214.78.120.0/22`) → US
- `2001:218::1` (in `2001:218::/32`) → JP
- `2001:220::1` (in `2001:220::1/128`) → KR

For multi-database testing, `89.160.20.112` is useful as it exists in multiple test databases:
- GeoIP2-Country-Test (`/28`) → SE
- GeoIP2-City-Test (`/28`) → SE, Linköping
- GeoIP2-ISP-Test (`/29`) → Linköping Universitet

This IP is good for testing field merging and smallest-network selection.

## Linting

Uses ruff (linting + formatting) and mypy (type checking), orchestrated via precious (`precious lint -g`).

For Splunk Cloud compatibility, use `splunk-appinspect` to validate the built package:
```bash
precious lint --command appinspect geoip-1.0.0.tar.gz
```

This runs AppInspect with the `cloud` tag to check for Splunk Cloud deployment requirements. The tarball is gitignored, so this must be run explicitly after building (not included in `precious lint -g`).

## Key Configuration Files

### globalConfig.json

The main UCC configuration file. Defines:
- Configuration tabs (accounts, databases, logging)
- Custom search commands (use `defaultValue` not `default` for argument defaults)
- UI settings

#### Configuration Tab Types

Tabs in `pages.configuration.tabs` can be either **multi-instance tables** or **single-instance forms**:

**Multi-instance table** (for multiple accounts/configurations):
```json
{
    "name": "account",
    "table": {
        "actions": ["edit", "delete", "clone"],
        "header": [{"label": "Name", "field": "name"}]
    },
    "entity": [
        {"field": "name", "required": true, ...},
        {"field": "api_key", "encrypted": true, ...}
    ],
    "title": "Accounts"
}
```
- Has `table` property with actions and header columns
- Requires a `name` field to identify each instance
- UI shows a table with add/edit/delete actions

**Single-instance form** (for one set of settings):
```json
{
    "name": "account",
    "entity": [
        {"field": "account_id", "encrypted": true, ...},
        {"field": "license_key", "encrypted": true, ...}
    ],
    "title": "MaxMind Account"
}
```
- No `table` property
- No `name` field needed
- UI shows a simple form with save button

#### Field Encryption

Use `"encrypted": true` on sensitive fields (API keys, passwords). UCC stores these in Splunk's secure credential storage (`passwords.conf`) rather than plain text config files.

### package/app.manifest

JSON file with add-on metadata. Note: The `version` field here should match `globalConfig.json` for consistency, but UCC uses the version from `globalConfig.json` as the source of truth and overwrites `app.manifest` during build.

```json
{
  "info": {
    "author": [{"name": "...", "email": "...", "company": "..."}],
    "title": "...",
    "description": "..."
  }
}
```

### package/default/app.conf

Custom settings merged into the generated `app.conf`. Example:
```ini
[launcher]
author = MaxMind
```

### package/default/commands.conf

Custom search command configuration. Unlike `app.conf`, UCC **replaces** (not merges) this file, so you must include all required settings:
```ini
[geoip]
filename = geoip.py
chunked = true
python.version = python3
python.required = 3.13
```

- `chunked = true` is required for streaming commands using the Splunk SDK
- `python.version` is for backward compatibility with Splunk < 10.2
- `python.required` is used by Splunk 10.2+ (takes precedence over `python.version`)

## Dependencies

There are three places where dependencies are managed:

- **Dev tools**: `mise.toml` - Python, uv, precious (managed by mise)
- **Build/dev dependencies**: `pyproject.toml` - pytest, mypy, ruff, UCC framework (managed by uv)
- **Add-on runtime dependencies**: `package/lib/requirements.txt` - splunktaucclib, splunk-sdk, solnlib, maxminddb, aiohttp, filelock, tenacity (installed into add-on's lib/ at build time)

### Updating Dependencies

To update all dependencies:

```bash
# Check for latest versions of mise tools
mise latest aqua:astral-sh/uv
mise latest github:houseabsolute/precious

# After updating mise.toml, regenerate the lock file
mise lock

# Check for latest Python package versions (example)
curl -s https://pypi.org/pypi/ruff/json | python3 -c "import sys, json; print(json.load(sys.stdin)['info']['version'])"

# After updating pyproject.toml, sync the lock file
uv sync

# Verify everything works
precious tidy -g && precious lint -g && uv run pytest tests && ./build.sh
```

**Important**: Keep Python on 3.13.x as that is the latest major version Splunk supports. When updating `maxminddb` in both `pyproject.toml` (dev) and `requirements.txt` (runtime), ensure versions stay in sync.

## UCC Framework Behavior

- UCC generates `.conf` files in the output `default/` directory
- For `app.conf`: UCC merges your settings with generated ones
- For `commands.conf`: UCC **replaces** the generated file entirely with yours (include all required settings)
- UCC automatically sets `python.version = python3` in generated `commands.conf` and `inputs.conf`
- Warning about "not auto generated by UCC framework" for custom settings is expected
- `ucc-gen init` creates a `README.md` in the addon source directory, but it's not needed and doesn't get included in the output package. Use `package/README.md` for end-user documentation instead.
- `additional_packaging.py` is a UCC post-build hook called by `ucc-gen build`. It copies `LICENSE-MIT` and `LICENSE-APACHE` from the repo root into `output/geoip/LICENSES/`, and `README.md` into `output/geoip/`.

### Custom Search Command File Naming

UCC generates a wrapper script for custom search commands. The naming works as follows:

- `globalConfig.json` specifies `commandName` (e.g., `"geoip"`) and `fileName` (e.g., `"geoip_command.py"`)
- UCC generates a wrapper named `<commandName>.py` (e.g., `geoip.py`) that imports from your `fileName`
- `commands.conf` must reference the **wrapper** name (`filename = geoip.py`), not the source file

The generated wrapper (`output/.../bin/geoip.py`) looks like:
```python
from geoip_command import stream

class GeoipCommand(StreamingCommand):
    def stream(self, events):
        return stream(self, events)
```

So the source file (`geoip_command.py`) and wrapper (`geoip.py`) are intentionally different files.

### Custom REST Handlers

Custom REST handlers allow you to add logic when configuration is saved. We use this to trigger background database updates when users save credentials or add databases.

**How it works:**

UCC generates REST handler files (`geoip_rh_*.py`) that handle API requests for configuration tabs. You can customize these handlers to add pre/post-save logic.

**For multi-instance tables** (like the databases tab), use `restHandlerModule` and `restHandlerClass` in `globalConfig.json`:

```json
{
    "name": "databases",
    "table": {...},
    "entity": [...],
    "restHandlerModule": "geoip_handler",
    "restHandlerClass": "GeoipDatabasesHandler"
}
```

UCC generates a wrapper (`geoip_rh_databases.py`) that imports your class from `geoip_handler.py` and uses it as the handler. Your module only needs the handler class - UCC generates the endpoint/field definitions.

**For single-instance forms** (like the account tab), `restHandlerModule`/`restHandlerClass` don't work. You must provide the complete handler file (`geoip_rh_settings.py`) with:
- Field definitions (duplicated from `globalConfig.json`)
- Endpoint setup (`MultipleModel`)
- Custom handler class

This duplication is unavoidable - UCC either generates the entire file OR copies yours; it can't merge them.

**Files involved:**

| File | Purpose |
|------|---------|
| `geoip_handler.py` | Shared module with `GeoipDatabasesHandler` class and background update functions |
| `geoip_rh_settings.py` | Complete custom handler for account/logging settings (field definitions duplicated) |
| `geoip_rh_databases.py` | UCC-generated wrapper that imports `GeoipDatabasesHandler` |

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

**Important:** Don't call `util.remove_http_proxy_env_vars()` in custom handlers if you need proxy support for external API calls (like downloading from MaxMind).

## Splunk Python Version Configuration

In Splunk 10.2+, `python.version` is deprecated. Use `python.required` instead:
- `python.required = 3.13` uses just the version number (not "python3.13")
- Default `python.version = python3` resolves to Python 3.9 in Splunk 10.2, not the latest
- Include both settings for backward compatibility with older Splunk versions
- The `maxminddb` 3.0.0 package requires Python 3.10+ (uses `kw_only` in dataclasses)

## Reinstalling the Add-on

When reinstalling, fully remove the old app first to avoid cached libraries:
```bash
splunk remove app geoip
splunk restart
splunk install app /path/to/geoip-1.0.0.tar.gz
```

## Logging

Logging uses solnlib to write to `$SPLUNK_HOME/var/log/splunk/{logger_name}.log`. The log level is configured via the Logging tab in the add-on's UI.

The shared `get_logger(session_key)` function in `geoip_utils.py` is used by all modules (search command, modular input, REST handlers). It's decorated with `@lru_cache(maxsize=1)` to avoid repeated REST API calls to read the log level setting.

```python
@lru_cache(maxsize=1)
def get_logger(session_key: str) -> logging.Logger:
    if not _HAS_SOLNLIB:
        fallback = logging.getLogger(APP_NAME)
        fallback.setLevel(logging.INFO)
        return fallback

    logger: logging.Logger = solnlib_log.Logs().get_logger(APP_NAME)
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=APP_NAME,
        conf_name=CONF_NAME,
    )
    logger.setLevel(log_level)
    return logger
```

### Key Points

- **Log file location**: `$SPLUNK_HOME/var/log/splunk/{logger_name}.log` - use the app name as logger name for consistency
- **Session key**: Required to read log level from settings. Available via `command.metadata.searchinfo.session_key` in streaming commands
- **Caching**: The logger is cached with `lru_cache` so only the first call per process makes a REST API call. Only one entry is cached; concurrent searches with different session keys evict each other, which is fine since the log level is global
- **Logging tab**: Add `{"type": "loggingTab"}` to `globalConfig.json` configuration tabs. Settings are stored in `{app_name}_settings.conf` under the `[logging]` stanza with a `loglevel` field
- **Don't use `set_context(namespace=...)`**: This prefixes the log filename, resulting in `{namespace}_{logger_name}.log` instead of just `{logger_name}.log`

## CI

GitHub Actions workflows run on push and pull request:

- **test.yml**: Runs `uv run pytest tests` on Ubuntu
- **lint.yml**: Runs `precious tidy --check -a`, `precious lint -a`, builds the package, and runs AppInspect
- **codeql-analysis.yml**: CodeQL security scanning (also weekly)
- **zizmor.yml**: Audits workflow files for security issues

Dependabot is configured to update uv dependencies and GitHub Actions versions daily.

## Key Constraints

- Always run tidying (`precious tidy -g`), linters (`precious lint -g`), tests (`uv run pytest tests`), and `./build.sh` before considering any changes complete
- The `author` field in `package/default/app.conf` must exactly match the first author name in `package/app.manifest`
