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

End-user documentation is in `package/README.md`.

### Command Architecture

The command implementation in `geoip_command.py` exposes a `stream(command, events)` function that the UCC-generated wrapper calls. The `command` parameter follows a `Protocol` with:
- `databases`, `field`, `prefix` - command arguments
- `metadata.searchinfo.session_key` - Splunk session key for API calls (e.g., reading settings)
- `metadata.searchinfo.app` - the app name

Database readers are cached at module level in `_readers`. This means:
- Databases are opened once and reused across events (good for performance)
- If a database file is updated on disk, the old data continues to be served until the process restarts
- The TODOs in the code note that database reloading needs to be implemented

## Build Commands

```bash
# Setup environment
mise install                      # Install Python 3.13
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
geoip/
├── globalConfig.json      # Main configuration file for UCC framework
├── package/
│   ├── app.manifest       # Add-on metadata (author, version, description)
│   ├── README.md          # End-user documentation (included in package)
│   ├── default/
│   │   ├── app.conf       # Splunk app configuration (merged with generated)
│   │   └── commands.conf  # Search command configuration (replaces generated)
│   ├── bin/               # Python scripts (inputs, custom commands)
│   ├── lib/
│   │   └── requirements.txt  # Python dependencies for the add-on
│   ├── static/            # Icons and images
│   └── data/              # Data files (e.g., MaxMind databases)
```

## Tests

Tests live in `tests/` and use pytest. Test data comes from the `MaxMind-DB` git submodule at `tests/data/`.

```
tests/
├── conftest.py              # Sets MAXMIND_DB_DIR to test database directory
├── data/                    # MaxMind-DB submodule (git submodule)
│   └── test-data/           # Contains test .mmdb files
└── geoip_command_test.py    # Tests using various test databases
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
- Configuration tabs (accounts, logging)
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
- **Add-on runtime dependencies**: `package/lib/requirements.txt` - splunktaucclib, splunk-sdk, solnlib, maxminddb (installed into add-on's lib/ at build time)

### Updating Dependencies

To update all dependencies:

```bash
# Check for latest versions of mise tools
mise latest uv
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

## Logging in Custom Search Commands

Logging uses solnlib to write to `$SPLUNK_HOME/var/log/splunk/{logger_name}.log`. The log level is configured via the Logging tab in the add-on's UI.

### Setup Pattern

```python
# At module level - import solnlib if available
try:
    from solnlib import conf_manager
    from solnlib import log as solnlib_log
    _HAS_SOLNLIB = True
except ImportError:
    _HAS_SOLNLIB = False

# Logger creation function (called lazily when needed)
def _get_logger(session_key: str) -> logging.Logger:
    if not _HAS_SOLNLIB:
        fallback = logging.getLogger(_APP_NAME)
        fallback.setLevel(logging.INFO)
        return fallback

    logger: logging.Logger = solnlib_log.Logs().get_logger(_APP_NAME)
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=_APP_NAME,
        conf_name=f"{_APP_NAME}_settings",
    )
    logger.setLevel(log_level)
    return logger
```

### Key Points

- **Log file location**: `$SPLUNK_HOME/var/log/splunk/{logger_name}.log` - use the app name as logger name for consistency
- **Session key**: Required to read log level from settings. Available via `command.metadata.searchinfo.session_key` in streaming commands
- **Lazy initialization**: Create the logger only when needed (e.g., inside exception handlers) to avoid overhead when no logging occurs
- **Logging tab**: Add `{"type": "loggingTab"}` to `globalConfig.json` configuration tabs. Settings are stored in `{app_name}_settings.conf` under the `[logging]` stanza with a `loglevel` field
- **Don't use `set_context(namespace=...)`**: This prefixes the log filename, resulting in `{namespace}_{logger_name}.log` instead of just `{logger_name}.log`

## Key Constraints

- Always run tidying (`precious tidy -g`), linters (`precious lint -g`), tests (`uv run pytest tests`), and `./build.sh` before considering any changes complete
- The `author` field in `package/default/app.conf` must exactly match the first author name in `package/app.manifest`
